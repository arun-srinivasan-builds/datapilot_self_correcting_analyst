"""Safe staging: dataset store, per-run directories, artifact collection, cleanup."""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import shutil
import stat
import time
from dataclasses import dataclass
from pathlib import Path

from sandbox_service.broker.config import BrokerConfig

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXEC_ID_RE = re.compile(r"^[A-Za-z0-9]{8,64}$")
ARTIFACT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
ARTIFACT_EXTENSIONS = (".png", ".json", ".csv", ".txt")
DATASET_KINDS = ("csv", "xlsx")
REPARSE_POINT = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT (Windows symlinks / junctions)
CHUNK = 1024 * 256


@dataclass(frozen=True, slots=True)
class Artifact:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class Collected:
    artifacts: list[Artifact]
    rejected: list[dict[str, str]]


class Layout:
    """Directory layout below the broker root; nothing outside `root` is ever used."""

    def __init__(self, cfg: BrokerConfig) -> None:
        self.root = cfg.root
        self.datasets = cfg.root / "datasets"
        self.runs = cfg.root / "runs"
        self.artifacts = cfg.root / "artifacts"

    def ensure(self) -> None:
        for path in (self.datasets, self.runs, self.artifacts):
            path.mkdir(parents=True, exist_ok=True)
            with contextlib.suppress(OSError):
                path.chmod(0o700)

    def dataset_path(self, sha: str, kind: str) -> Path:
        return self.datasets / f"{sha}.{kind}"

    def find_dataset(self, sha: str) -> tuple[Path, str] | None:
        if not SHA256_RE.match(sha):
            return None
        for kind in DATASET_KINDS:
            path = self.dataset_path(sha, kind)
            if path.is_file():
                return path, kind
        return None

    def run_dir(self, exec_id: str) -> Path:
        return self.runs / exec_id

    def artifact_dir(self, exec_id: str) -> Path:
        return self.artifacts / exec_id


def valid_dataset_magic(kind: str, head: bytes) -> bool:
    if kind == "xlsx":
        return head.startswith(b"PK\x03\x04")
    return b"\x00" not in head and not head.startswith(b"PK\x03\x04")


def store_dataset_stream(layout: Layout, sha: str, kind: str, reader, length: int) -> str:
    """Stream `length` bytes into a temp file, verify the SHA-256, then publish atomically.

    Returns "created" or "exists". Raises ValueError("digest_mismatch" | "bad_content").
    """
    final = layout.dataset_path(sha, kind)
    if final.is_file():
        remaining = length
        while remaining > 0:  # drain the body so the connection stays well-formed
            chunk = reader(min(CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
        return "exists"
    tmp = layout.datasets / f".upload-{os.getpid()}-{time.monotonic_ns()}"
    digest = hashlib.sha256()
    head = b""
    try:
        with tmp.open("wb") as handle:
            remaining = length
            while remaining > 0:
                chunk = reader(min(CHUNK, remaining))
                if not chunk:
                    raise ValueError("bad_content")
                if len(head) < 4096:
                    head += chunk[: 4096 - len(head)]
                digest.update(chunk)
                handle.write(chunk)
                remaining -= len(chunk)
        if digest.hexdigest() != sha:
            raise ValueError("digest_mismatch")
        if not valid_dataset_magic(kind, head):
            raise ValueError("bad_content")
        os.replace(tmp, final)
        with contextlib.suppress(OSError):
            final.chmod(0o444)
        return "created"
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


def dir_size(path: Path) -> int:
    total = 0
    with contextlib.suppress(OSError):
        for entry in os.scandir(path):
            with contextlib.suppress(OSError):
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
    return total


def _is_link_like(entry: os.DirEntry[str]) -> bool:
    if entry.is_symlink():
        return True
    attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
    return bool(attrs & REPARSE_POINT)


def collect_artifacts(out_dir: Path, dest: Path, cfg: BrokerConfig) -> Collected:
    """Copy allow-listed regular files out of the (stopped) container's output directory.

    Rejected: symlinks/reparse points, directories, odd names or extensions, oversize files, and
    anything past the count/total caps. Files are re-checked on the open file descriptor.
    """
    artifacts: list[Artifact] = []
    rejected: list[dict[str, str]] = []
    total = 0
    for entry in sorted(os.scandir(out_dir), key=lambda e: e.name):
        name = entry.name

        def reject(reason: str, *, _name: str = name) -> None:
            rejected.append({"name": _name[:80], "reason": reason})

        if _is_link_like(entry):
            reject("symlink")
        elif entry.is_dir(follow_symlinks=False):
            reject("directory")
        elif not ARTIFACT_NAME_RE.match(name) or not name.lower().endswith(ARTIFACT_EXTENSIONS):
            reject("name_or_extension_not_allowed")
        elif len(artifacts) >= cfg.max_artifacts:
            reject("too_many_files")
        else:
            st = entry.stat(follow_symlinks=False)
            if not stat.S_ISREG(st.st_mode):
                reject("not_regular_file")
            elif st.st_size > cfg.max_artifact_bytes:
                reject("file_too_large")
            elif total + st.st_size > cfg.max_out_total_bytes:
                reject("total_too_large")
            else:
                dest.mkdir(parents=True, exist_ok=True)  # only when there is something to keep
                copied = _copy_regular(Path(entry.path), dest / name, st.st_size, cfg)
                if copied is None:
                    reject("changed_or_unreadable")
                else:
                    total += copied.size
                    artifacts.append(Artifact(name, copied.size, copied.sha256))
    if dest.is_dir() and not artifacts:
        with contextlib.suppress(OSError):
            dest.rmdir()  # a failed copy must not leave an empty directory behind
    return Collected(artifacts, rejected)


def _copy_regular(src: Path, dst: Path, expected: int, cfg: BrokerConfig) -> Artifact | None:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(src, flags)
    except OSError:
        return None
    digest = hashlib.sha256()
    size = 0
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != expected:
            return None
        with dst.open("wb") as out:
            while chunk := handle.read(CHUNK):
                size += len(chunk)
                if size > cfg.max_artifact_bytes:
                    break
                digest.update(chunk)
                out.write(chunk)
    if size > cfg.max_artifact_bytes:
        with contextlib.suppress(OSError):
            dst.unlink()
        return None
    return Artifact(dst.name, size, digest.hexdigest())


def remove_tree(path: Path) -> None:
    def onerror(func, p, _exc):  # read-only files on Windows
        with contextlib.suppress(OSError):
            os.chmod(p, stat.S_IWRITE)
            func(p)

    if path.is_symlink():
        with contextlib.suppress(OSError):
            path.unlink()
    elif path.exists():
        shutil.rmtree(path, onerror=onerror)


def reap_stale(layout: Layout, cfg: BrokerConfig, *, active: set[str]) -> list[str]:
    """Remove run dirs that no live run owns and artifact dirs older than the TTL."""
    removed: list[str] = []
    for child in layout.runs.iterdir():
        if child.name not in active:
            remove_tree(child)
            removed.append(f"runs/{child.name}")
    for child in layout.datasets.glob(".upload-*"):
        with contextlib.suppress(OSError):
            child.unlink()
    removed += reap_expired(layout, cfg)
    return removed


def reap_expired(layout: Layout, cfg: BrokerConfig) -> list[str]:
    """Age-based retention only (safe while runs are active): datasets and old artifacts."""
    removed: list[str] = []
    now = time.time()
    for child in layout.datasets.iterdir():
        if not child.name.startswith(".") and now - child.stat().st_mtime > cfg.dataset_ttl_s:
            with contextlib.suppress(OSError):
                os.chmod(child, stat.S_IWRITE)
                child.unlink()
                removed.append(f"datasets/{child.name}")
    for child in layout.artifacts.iterdir():
        if now - child.stat().st_mtime > cfg.artifact_ttl_s:
            remove_tree(child)
            removed.append(f"artifacts/{child.name}")
    return removed

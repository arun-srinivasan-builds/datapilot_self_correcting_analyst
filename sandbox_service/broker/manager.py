"""Run lifecycle: stage -> create -> start -> watchdog -> collect -> always clean up."""

from __future__ import annotations

import contextlib
import logging
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from sandbox_service.broker.config import BrokerConfig, ImageLock
from sandbox_service.broker.runtime import ContainerRuntime, ContainerSpec
from sandbox_service.broker.staging import (
    Collected,
    Layout,
    collect_artifacts,
    dir_size,
    reap_expired,
    reap_stale,
    remove_tree,
)

log = logging.getLogger("sandbox.manager")
POLL_S = 0.05
SLOW_RUN_MS = 20_000
SIZE_CHECK_S = 0.25


def _ms_since(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


class Busy(Exception):
    """All execution slots are in use."""


class Conflict(Exception):
    """An execution with this id already exists."""


@dataclass
class ActiveRun:
    cancel: threading.Event = field(default_factory=threading.Event)


class _Drain(threading.Thread):
    """Reads a pipe fully (so the container never blocks) but keeps only `cap` bytes."""

    def __init__(self, stream: Any, cap: int) -> None:
        super().__init__(daemon=True)
        self._stream, self._cap = stream, cap
        self.data = bytearray()
        self.truncated = False

    def run(self) -> None:
        for chunk in iter(lambda: self._stream.read(65536), b""):
            room = self._cap - len(self.data)
            if room > 0:
                self.data += chunk[:room]
            if len(chunk) > max(room, 0):
                self.truncated = True


class RunManager:
    def __init__(self, cfg: BrokerConfig, runtime: ContainerRuntime, lock: ImageLock) -> None:
        self.cfg, self.runtime, self.lock = cfg, runtime, lock
        self.layout = Layout(cfg)
        self.layout.ensure()
        self._active: dict[str, ActiveRun] = {}
        self._mutex = threading.Lock()
        self._slots = threading.BoundedSemaphore(cfg.max_concurrent)
        self.timing_log: deque[dict[str, Any]] = deque(maxlen=500)  # per-phase latency diagnostics

    # -- lifecycle ---------------------------------------------------------------------------
    def startup_reap(self) -> dict[str, list[str]]:
        """Remove every managed container and stale directory left by a previous broker."""
        containers = self.runtime.list_managed()
        for name in containers:
            self.runtime.remove(name)
        with self._mutex:
            active = set(self._active)
        dirs = reap_stale(self.layout, self.cfg, active=active)
        log.info("startup reaper removed %d containers, %d directories", len(containers), len(dirs))
        return {"containers": containers, "directories": dirs}

    def cancel(self, exec_id: str) -> bool:
        with self._mutex:
            run = self._active.get(exec_id)
        if run:
            run.cancel.set()
        return run is not None

    def delete(self, exec_id: str) -> bool:
        cancelled = self.cancel(exec_id)
        existed = self.layout.artifact_dir(exec_id).exists()
        remove_tree(self.layout.artifact_dir(exec_id))
        return cancelled or existed

    def shutdown(self) -> None:
        with self._mutex:
            runs = list(self._active.values())
        for run in runs:
            run.cancel.set()

    # -- one execution -----------------------------------------------------------------------
    def run(
        self,
        exec_id: str,
        code: str,
        dataset_path: Any,
        dataset_kind: str,
        sheet: str | None,
        timeout_s: int,
    ) -> dict[str, Any]:
        if not self._slots.acquire(blocking=False):
            raise Busy
        active = ActiveRun()
        try:
            with self._mutex:
                if exec_id in self._active or self.layout.artifact_dir(exec_id).exists():
                    raise Conflict
                self._active[exec_id] = active
            return self._execute(
                active, exec_id, code, dataset_path, dataset_kind, sheet, timeout_s
            )
        finally:
            with self._mutex:
                self._active.pop(exec_id, None)
            self._slots.release()
            with contextlib.suppress(OSError):
                reap_expired(self.layout, self.cfg)

    def _execute(
        self,
        active: ActiveRun,
        exec_id: str,
        code: str,
        dataset_path: Any,
        dataset_kind: str,
        sheet: str | None,
        timeout_s: int,
    ) -> dict[str, Any]:
        cfg, name = self.cfg, f"{self.cfg.container_prefix}{exec_id}"
        run_dir = self.layout.run_dir(exec_id)
        in_dir, out_dir = run_dir / "in", run_dir / "out"
        started = time.monotonic()
        container_made = False
        timing: dict[str, int] = {}
        try:
            in_dir.mkdir(parents=True)
            out_dir.mkdir()
            (in_dir / "analysis.py").write_text(code, encoding="utf-8", newline="\n")
            shutil.copyfile(dataset_path, in_dir / f"data.{dataset_kind}")
            self._permissions(in_dir, out_dir)
            env = {
                "DATA_PATH": f"/in/data.{dataset_kind}",
                "OUTPUT_DIR": "/out",
                "MPLBACKEND": "Agg",
                "PYTHONHASHSEED": "0",
                "TZ": "UTC",
                "HOME": "/tmp",  # noqa: S108 - container-internal tmpfs
                "MPLCONFIGDIR": "/tmp/mpl",  # noqa: S108
            }
            if sheet:
                env["SHEET"] = sheet
            spec = ContainerSpec(
                name=name,
                exec_id=exec_id,
                image_id=self.lock.image_id,
                in_dir=in_dir.resolve(),
                out_dir=out_dir.resolve(),
                env=env,
                memory=cfg.memory,
                cpus=cfg.cpus,
                pids=cfg.pids,
                fsize_bytes=cfg.max_artifact_bytes * 4,
            )
            container_made = True
            t = time.monotonic()
            timing["stage_ms"] = int((t - started) * 1000)
            self.runtime.create(spec)
            timing["create_ms"] = _ms_since(t)
            t = time.monotonic()
            reason, proc, out, err = self._watch(active, name, out_dir, timeout_s)
            timing["run_ms"] = _ms_since(t)
            t = time.monotonic()
            state = self.runtime.state(name)
            timing["inspect_ms"] = _ms_since(t)
            t = time.monotonic()
            result = self._result(exec_id, reason, proc, state, out, err, out_dir, started)
            timing["collect_ms"] = _ms_since(t)
            return result
        except BaseException:
            remove_tree(self.layout.artifact_dir(exec_id))  # never keep partial output on failure
            raise
        finally:
            t = time.monotonic()
            if container_made:
                self.runtime.remove(name)
            timing["remove_ms"] = _ms_since(t)
            remove_tree(run_dir)
            timing["total_ms"] = _ms_since(started)
            self.timing_log.append({"exec_id": exec_id, **timing})
            if timing["total_ms"] > SLOW_RUN_MS:
                log.warning("slow sandbox run %s: %s", exec_id, timing)

    def _watch(
        self, active: ActiveRun, name: str, out_dir: Any, timeout_s: int
    ) -> tuple[str | None, subprocess.Popen[bytes], _Drain, _Drain]:
        proc = self.runtime.start_attached(name)
        assert proc.stdout is not None and proc.stderr is not None  # noqa: S101
        out = _Drain(proc.stdout, self.cfg.output_cap_bytes)
        err = _Drain(proc.stderr, self.cfg.output_cap_bytes)
        out.start()
        err.start()
        deadline = time.monotonic() + timeout_s
        next_size = time.monotonic() + SIZE_CHECK_S
        reason: str | None = None
        while proc.poll() is None:
            now = time.monotonic()
            if active.cancel.is_set():
                reason = "cancelled"
            elif now > deadline:
                reason = "timeout"
            elif now >= next_size:
                next_size = now + SIZE_CHECK_S
                if dir_size(out_dir) > self.cfg.max_out_total_bytes:
                    reason = "output_limit"
            if reason:
                self.runtime.kill(name)
                break
            time.sleep(POLL_S)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        out.join(5)
        err.join(5)
        return reason, proc, out, err

    def _result(
        self,
        exec_id: str,
        reason: str | None,
        proc: subprocess.Popen[bytes],
        state: Any,
        out: _Drain,
        err: _Drain,
        out_dir: Any,
        started: float,
    ) -> dict[str, Any]:
        stderr = bytes(err.data).decode("utf-8", "replace")
        if reason == "timeout":
            status, code = "timeout", 124
            stderr += "\n[sandbox] wall-clock limit reached; execution killed"
        elif reason == "cancelled":
            status, code = "killed", 137
            stderr += "\n[sandbox] execution cancelled"
        elif reason == "output_limit":
            status, code = "killed", 137
            stderr += "\n[sandbox] output size limit exceeded; execution killed"
        elif state.oom_killed:
            status, code = "killed", 137
            stderr += "\n[sandbox] out of memory; execution killed"
        else:
            code = state.exit_code if state.exit_code >= 0 else (proc.returncode or 1)
            status = "ok" if code == 0 else "error"
        if reason == "cancelled":  # a cancelled execution leaves no artifacts behind
            collected = Collected([], [])
        else:
            collected = self._collect(exec_id, out_dir)
        return self._payload(exec_id, status, code, out, err, stderr, collected, started)

    def _collect(self, exec_id: str, out_dir: Any) -> Collected:
        try:
            return collect_artifacts(out_dir, self.layout.artifact_dir(exec_id), self.cfg)
        except OSError:  # the run directory was reaped underneath us (broker restart)
            remove_tree(self.layout.artifact_dir(exec_id))  # created before the scan failed
            return Collected([], [{"name": "*", "reason": "run_directory_removed"}])

    @staticmethod
    def _payload(
        exec_id: str,
        status: str,
        code: int,
        out: _Drain,
        err: _Drain,
        stderr: str,
        collected: Collected,
        started: float,
    ) -> dict[str, Any]:
        return {
            "exec_id": exec_id,
            "status": status,
            "exit_code": code,
            "stdout": bytes(out.data).decode("utf-8", "replace"),
            "stderr": stderr,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "artifacts": [
                {"name": a.name, "size": a.size, "sha256": a.sha256} for a in collected.artifacts
            ],
            "rejected_artifacts": collected.rejected,
            "truncated": out.truncated or err.truncated,
        }

    @staticmethod
    def _permissions(in_dir: Any, out_dir: Any) -> None:
        # On POSIX hosts the container user (10001) must write /out and only read /in.
        with contextlib.suppress(OSError):
            in_dir.chmod(0o755)
            (in_dir / "analysis.py").chmod(0o644)
            out_dir.chmod(0o777)

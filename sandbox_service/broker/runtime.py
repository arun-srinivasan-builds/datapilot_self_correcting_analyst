"""Container runtime adapter. The broker builds every command; requests never contribute flags.

Only `DockerRuntime` exists today. A `PodmanRuntime` can implement the same protocol later; nothing
above this module depends on which runtime is behind it (PRP §6.4).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

log = logging.getLogger("sandbox.runtime")
LABEL = "datapilot.sandbox"
CMD = ("python", "-I", "/in/analysis.py")
CLI_TIMEOUT = 30  # every engine call is bounded: a stalled Docker API must not stall a run
SLOW_CLI_S = 5.0


@dataclass(frozen=True, slots=True)
class ContainerSpec:
    name: str
    exec_id: str
    image_id: str
    in_dir: Path
    out_dir: Path
    env: Mapping[str, str]
    memory: str
    cpus: str
    pids: int
    fsize_bytes: int


@dataclass(frozen=True, slots=True)
class ContainerState:
    exit_code: int
    oom_killed: bool


class ContainerRuntime(Protocol):
    def verify_image(self, image_id: str) -> None: ...
    def create(self, spec: ContainerSpec) -> None: ...
    def start_attached(self, name: str) -> subprocess.Popen[bytes]: ...
    def kill(self, name: str) -> None: ...
    def state(self, name: str) -> ContainerState: ...
    def remove(self, name: str) -> None: ...
    def list_managed(self) -> list[str]: ...
    def capabilities(self) -> dict[str, object]: ...


def build_create_argv(docker: str, spec: ContainerSpec) -> list[str]:
    """The one and only way a container is created. Fixed flags; nothing request-controlled
    except the validated exec id (in names/labels) and the validated SHEET value (an env value)."""
    argv = [
        docker,
        "create",
        "--name",
        spec.name,
        "--label",
        f"{LABEL}=1",
        "--label",
        f"{LABEL}.exec={spec.exec_id}",
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        "10001:10001",
        "--memory",
        spec.memory,
        "--memory-swap",
        spec.memory,
        "--cpus",
        spec.cpus,
        "--pids-limit",
        str(spec.pids),
        "--ulimit",
        "nofile=256:256",
        "--ulimit",
        "core=0",
        "--ulimit",
        f"fsize={spec.fsize_bytes}:{spec.fsize_bytes}",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=64m",  # noqa: S108 - container-internal tmpfs
        "--shm-size",
        "16m",
        "--log-driver",
        "none",
        "--stop-timeout",
        "1",
        "--no-healthcheck",
        "--mount",
        f"type=bind,source={spec.in_dir},target=/in,readonly",
        "--mount",
        f"type=bind,source={spec.out_dir},target=/out",
    ]
    for key, value in spec.env.items():
        argv += ["-e", f"{key}={value}"]
    argv += [spec.image_id, *CMD]
    return argv


class DockerRuntime:
    def __init__(self, docker: str | None = None) -> None:
        found = docker or shutil.which("docker")
        if not found:
            raise RuntimeError("docker CLI not found")
        self._docker = found

    def _run(
        self, args: Sequence[str], *, check: bool = True, timeout: int = CLI_TIMEOUT
    ) -> subprocess.CompletedProcess[str]:
        started = time.monotonic()
        try:
            return subprocess.run(  # noqa: S603 - fixed argv, never a shell
                [self._docker, *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=check,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            log.error("docker %s timed out after %ss", args[0], timeout)
            raise
        finally:
            if (elapsed := time.monotonic() - started) > SLOW_CLI_S:
                log.warning("slow docker call: %s took %.1fs", args[0], elapsed)

    def verify_image(self, image_id: str) -> None:
        proc = self._run(["image", "inspect", image_id, "--format", "{{.Id}}"], check=False)
        if proc.returncode != 0 or proc.stdout.strip() != image_id:
            raise RuntimeError("sandbox image is missing or does not match image.lock.json")

    def create(self, spec: ContainerSpec) -> None:
        argv = build_create_argv(self._docker, spec)
        proc = subprocess.run(  # noqa: S603
            argv, capture_output=True, text=True, timeout=CLI_TIMEOUT, stdin=subprocess.DEVNULL
        )
        if proc.returncode != 0:
            raise RuntimeError(f"container create failed: {proc.stderr.strip()[:300]}")

    def start_attached(self, name: str) -> subprocess.Popen[bytes]:
        return subprocess.Popen(  # noqa: S603
            [self._docker, "start", "-a", name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def _best_effort(self, args: Sequence[str]) -> subprocess.CompletedProcess[str] | None:
        """Cleanup-class calls: a stalled engine is logged, never allowed to hang or raise."""
        try:
            return self._run(args, check=False)
        except subprocess.TimeoutExpired:
            return None

    def kill(self, name: str) -> None:
        self._best_effort(["kill", name])

    def state(self, name: str) -> ContainerState:
        fmt = "{{.State.ExitCode}} {{.State.OOMKilled}}"
        proc = self._best_effort(["inspect", name, "--format", fmt])
        parts = proc.stdout.split() if proc else []
        if proc is None or proc.returncode != 0 or len(parts) != 2:
            return ContainerState(-1, False)
        return ContainerState(int(parts[0]), parts[1] == "true")

    def remove(self, name: str) -> None:
        if self._best_effort(["rm", "-f", "-v", name]) is None:
            log.error("could not remove container %s (engine stalled); the reaper will retry", name)

    def list_managed(self) -> list[str]:
        proc = self._run(
            ["ps", "-a", "--filter", f"label={LABEL}=1", "--format", "{{.Names}}"], check=False
        )
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]

    def capabilities(self) -> dict[str, object]:
        """Runtime-specific timeout facts, probed rather than assumed (decision C2)."""
        help_text = self._run(["run", "--help"], check=False).stdout
        version = self._run(["version", "--format", "{{.Server.Version}}"], check=False)
        return {
            "runtime": "docker",
            "server_version": version.stdout.strip(),
            "run_has_timeout_flag": "--timeout" in help_text,
            "run_has_stop_timeout_flag": "--stop-timeout" in help_text,
            "timeout_enforcement": "broker wall-clock watchdog: docker kill + docker rm -f",
        }

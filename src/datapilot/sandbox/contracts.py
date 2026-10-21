"""Framework-neutral execution contract between the agents and the sandbox (Stage 4 implements it).

The agents depend only on `ExecutionBackend`; they never know which runtime (Docker, Podman) or
transport (loopback HTTP, Unix socket) sits behind it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

ExecStatus = Literal["ok", "error", "timeout", "killed", "rejected"]


class SandboxUnavailableError(RuntimeError):
    """Infrastructure failure (broker unreachable, runtime down). Not a defect in generated code."""


@dataclass(frozen=True, slots=True)
class ArtifactInfo:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    status: ExecStatus
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    artifacts: tuple[ArtifactInfo, ...] = ()
    truncated: bool = False
    exec_id: str = ""
    results_json: str | None = None  # content of results.json when the run produced one

    @property
    def ok(self) -> bool:
        return self.status == "ok" and self.exit_code == 0


class ExecutionBackend(Protocol):
    async def run(self, code: str, *, run_id: str) -> ExecutionResult:
        """Execute one script in isolation. Raise `SandboxUnavailableError` on infra faults."""
        ...

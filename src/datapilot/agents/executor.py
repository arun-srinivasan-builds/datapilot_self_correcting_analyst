"""Executor-side bridge: an AutoGen `CodeExecutor` that runs code through an `ExecutionBackend`.

It is the only place where structured execution results are produced. They are recorded in
`RunState` (so routing and approval never parse text) and as `exec_started` / `exec_result` events,
then composed into the text the Coder receives (stderr verbatim, tail-truncated if huge).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from autogen_core import CancellationToken
from autogen_core.code_executor import CodeBlock, CodeExecutor, CodeResult

from datapilot.agents.termination import RunState
from datapilot.events import EventStore, EventType
from datapilot.reports.results import validate_results
from datapilot.sandbox.contracts import ExecutionBackend, ExecutionResult, SandboxUnavailableError

log = logging.getLogger(__name__)
MAX_FIELD_CHARS = 6000
EXECUTOR = "Executor"


def _sha256(text: str | None) -> str | None:
    return None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()


def code_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()[:12]


def _tail(text: str) -> str:
    if len(text) <= MAX_FIELD_CHARS:
        return text
    cut = len(text) - MAX_FIELD_CHARS
    return f"[... {cut} earlier characters truncated ...]\n{text[-MAX_FIELD_CHARS:]}"


def format_result(
    result: ExecutionResult, *, status: str | None = None, violations: list[str] | None = None
) -> str:
    parts = [f"status: {status or result.status}", f"exit_code: {result.exit_code}"]
    parts += ["--- stdout ---", _tail(result.stdout), "--- stderr ---", _tail(result.stderr)]
    if violations:
        parts += ["--- results.json contract violations ---", *[f"- {v}" for v in violations]]
    return "\n".join(parts)


class ObservedCodeExecutor(CodeExecutor):
    def __init__(
        self,
        backend: ExecutionBackend,
        state: RunState,
        store: EventStore,
        run_id: str,
        *,
        require_results: bool = True,
    ) -> None:
        self._require_results = require_results
        self._backend = backend
        self._state = state
        self._store = store
        self._run_id = run_id

    async def execute_code_blocks(
        self, code_blocks: list[CodeBlock], cancellation_token: CancellationToken
    ) -> CodeResult:
        self._state.begin_exec()
        if len(code_blocks) != 1 or code_blocks[0].language.strip().lower() != "python":
            return self._reject(len(code_blocks))
        code = code_blocks[0].code
        digest = code_hash(code)
        flag = self._injected_flag(digest)
        self._store.append(EventType.EXEC_STARTED, EXECUTOR, {"code_hash": digest, **flag})
        try:
            # Linking the token makes a run stop/timeout cancel the in-flight execution; the backend
            # must treat CancelledError as "kill the container and clean up" (Stage 4).
            execution = asyncio.ensure_future(self._backend.run(code, run_id=self._run_id))
            cancellation_token.link_future(execution)
            result = await execution
        except SandboxUnavailableError as exc:
            log.error("sandbox unavailable: %s", exc)
            self._state.record_exec("error", None)
            self._state.record_infra_error(f"sandbox unavailable: {exc}")
            self._store.append(
                EventType.EXEC_RESULT,
                EXECUTOR,
                {"status": "infra_error", "exit_code": None, "stderr": str(exc), "stdout": ""},
            )
            return CodeResult(exit_code=1, output=f"sandbox unavailable: {exc}")
        violations = self._contract_violations(result)
        status = "invalid_results" if violations else result.status
        self._state.record_exec(status, result.exit_code)
        if violations:
            self._store.append(
                EventType.GUARDRAIL,
                EXECUTOR,
                {"rule": "results_contract", "outcome": "rejected", "violations": violations},
            )
        self._store.append(
            EventType.EXEC_RESULT,
            EXECUTOR,
            {
                "status": status,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "violations": violations,
                "duration_ms": result.duration_ms,
                "artifacts": [
                    {"name": a.name, "size": a.size, "sha256": a.sha256} for a in result.artifacts
                ],
                "truncated": result.truncated,
                "exec_id": result.exec_id,
                "results_sha256": _sha256(result.results_json),
                "code_hash": digest,
                **flag,
            },
        )
        if result.ok and not violations:
            self._state.last_valid_result = result  # what a Reviewer approval would refer to
            self._state.last_valid_code_hash = digest
        if violations:
            text = format_result(result, status=status, violations=violations)
            return CodeResult(exit_code=3, output=text)
        return CodeResult(exit_code=result.exit_code, output=format_result(result))

    def _injected_flag(self, digest: str) -> dict[str, str]:
        fault = self._state.injected_hashes.get(digest)
        return {"injected_fault": fault} if fault else {}

    def _contract_violations(self, result: ExecutionResult) -> list[str]:
        if not self._require_results or not result.ok:
            return []
        return validate_results(result.results_json, {a.name for a in result.artifacts})

    def _reject(self, blocks: int) -> CodeResult:
        reason = f"exactly one ```python block is required, got {blocks}"
        self._state.record_exec("rejected", 2)
        payload: dict[str, Any] = {
            "rule": "single_python_block",
            "outcome": "rejected",
            "blocks": blocks,
        }
        self._store.append(EventType.GUARDRAIL, EXECUTOR, payload)
        self._store.append(
            EventType.EXEC_RESULT,
            EXECUTOR,
            {"status": "rejected", "exit_code": 2, "stdout": "", "stderr": reason},
        )
        return CodeResult(exit_code=2, output=f"status: rejected\nexit_code: 2\n{reason}")

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def restart(self) -> None:
        return None

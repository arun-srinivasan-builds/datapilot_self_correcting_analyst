"""Deterministic orchestration harness. TEST ONLY.

`ScriptedBackend` is a scripted stand-in for the sandbox. It exists so routing/termination can be
tested without a container runtime. Nothing produced with it is evidence of real sandbox execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autogen_ext.models.replay import ReplayChatCompletionClient

from datapilot.agents.participants import RoleClients
from datapilot.agents.runner import RunConfig, RunControl, run_question
from datapilot.agents.teams import Mode
from datapilot.agents.termination import RunOutcome
from datapilot.events import CanvasState, EventStore, reduce_events
from datapilot.sandbox.contracts import ExecutionResult

MODEL_INFO = {
    "vision": False,
    "function_calling": False,
    "json_output": False,
    "family": "unknown",
    "structured_output": False,
}
LETTER = {"Planner": "P", "Coder": "C", "Executor": "E", "Reviewer": "R"}
STDERR = "Traceback (most recent call last):\n  File \"analysis.py\", line 3\nKeyError: 'revenue'"
PROFILE: dict[str, Any] = {"rows": 3, "columns": [{"name": "units"}]}
OK = ExecutionResult("ok", 0, stdout="rows=3\nrevenue=42", duration_ms=5)
ERR = ExecutionResult("error", 1, stderr=STDERR, duration_ms=5)


def client(responses: list[str]) -> ReplayChatCompletionClient:
    return ReplayChatCompletionClient(chat_completions=list(responses), model_info=MODEL_INFO)


class ScriptedBackend:
    """Returns the next scripted ExecutionResult; an unexpected extra execution fails the test."""

    def __init__(self, results: list[ExecutionResult]) -> None:
        self._results = list(results)
        self.codes: list[str] = []

    async def run(self, code: str, *, run_id: str) -> ExecutionResult:
        self.codes.append(code)
        if len(self.codes) > len(self._results):
            raise AssertionError("unexpected extra execution")
        return self._results[len(self.codes) - 1]


@dataclass
class Run:
    outcome: RunOutcome
    store: EventStore
    backend: ScriptedBackend
    clients: RoleClients
    selector: ReplayChatCompletionClient

    @property
    def canvas(self) -> CanvasState:
        return reduce_events(self.store.snapshot())

    @property
    def letters(self) -> str:
        """Speaker order of the counted agent messages, e.g. `PCER`."""
        return "".join(
            LETTER[e.source] for e in self.store.snapshot() if e.type.value == "agent_message"
        )

    def types(self) -> list[str]:
        return [e.type.value for e in self.store.snapshot()]

    def of(self, type_: str) -> list[Any]:
        return [e for e in self.store.snapshot() if e.type.value == type_]


def parse(script: str) -> tuple[list[str], list[ExecutionResult], list[str]]:
    """`P C E✗ R P C E✓ R!` -> coder replies, execution results, reviewer replies."""
    coder: list[str] = []
    execs: list[ExecutionResult] = []
    reviewer: list[str] = []
    for step in script.split():
        if step == "C":
            n = len(coder) + 1
            coder.append(f"Revision {n}.\n```python\n# version {n}\nprint({n})\n```")
        elif step.startswith("E"):
            execs.append(OK if step.endswith("✓") else ERR)
        elif step.startswith("R"):
            reviewer.append(
                "All numbers match the output.\nAPPROVED"
                if step.endswith("!")
                else "1. The y axis needs a unit.\n2. State the comparison period."
            )
    return coder, execs, reviewer


async def run_script(
    script: str,
    mode: Mode = "selector",
    *,
    max_messages: int = 12,
    max_tokens: int = 10_000_000,
    planner: list[str] | None = None,
    coder: list[str] | None = None,
    reviewer: list[str] | None = None,
    execs: list[ExecutionResult] | None = None,
    timeout_seconds: int = 60,
    control: RunControl | None = None,
    backend: Any = None,
    require_results: bool = False,
) -> Run:
    c, e, r = parse(script)
    n_plan = script.split().count("P") or 1
    clients = RoleClients(
        planner=client(planner or ["1) pick columns\n2) aggregate\n3) chart"] * n_plan),
        coder=client(coder if coder is not None else c),
        reviewer=client(reviewer if reviewer is not None else r),
    )
    selector = client([])  # a selector LLM fallback call would raise: guarded routing never asks
    be = backend or ScriptedBackend(execs if execs is not None else e)
    store = EventStore("run-test")
    outcome = await run_question(
        question="Which category dropped most?",
        profile=PROFILE,
        config=RunConfig(
            mode, max_messages, max_tokens, timeout_seconds, require_results=require_results
        ),
        clients=clients,
        selector_client=selector,
        backend=be,
        store=store,
        control=control,
    )
    return Run(outcome, store, be, clients, selector)

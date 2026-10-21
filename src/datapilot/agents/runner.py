"""Run one question end to end: fresh team, stream it, record real events, return the outcome."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from autogen_agentchat.base import TaskResult
from autogen_core import CancellationToken
from autogen_core.models import ChatCompletionClient

from datapilot.agents.participants import RoleClients
from datapilot.agents.prompts import build_task
from datapilot.agents.teams import Mode, build_team
from datapilot.agents.termination import RunOutcome, RunState
from datapilot.config import Settings
from datapilot.events import EventStore, EventType
from datapilot.faults import FaultInjector
from datapilot.sandbox.contracts import ExecutionBackend

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RunConfig:
    mode: Mode = "selector"
    max_messages: int = 12
    max_tokens: int = 30_000
    timeout_seconds: int = 300
    require_results: bool = True
    completion_ceiling: int | None = None
    fault: FaultInjector | None = None  # TEST ONLY; from_settings never sets it

    @classmethod
    def from_settings(cls, settings: Settings, mode: Mode = "selector") -> RunConfig:
        return cls(
            mode,
            settings.max_agent_messages,
            settings.max_run_tokens,
            settings.run_timeout_seconds,
            completion_ceiling=settings.max_completion_tokens,
        )


@dataclass
class RunControl:
    """Lets another thread/task stop a run. The reason distinguishes STOPPED from TIMEOUT."""

    token: CancellationToken = field(default_factory=CancellationToken)
    reason: RunOutcome | None = None

    def stop(self) -> None:
        if self.reason is None:
            self.reason = RunOutcome.STOPPED
        self.token.cancel()


@dataclass(frozen=True)
class RunReport:
    """Outcome plus the final run state (counters, usage, last valid result) of one run."""

    outcome: RunOutcome
    state: RunState


async def run_question(**kwargs: Any) -> RunOutcome:
    """Run one question and return only its outcome (see `run_to_report` for the full state)."""
    return (await run_to_report(**kwargs)).outcome


async def run_to_report(
    *,
    question: str,
    profile: dict[str, Any],
    config: RunConfig,
    clients: RoleClients,
    selector_client: ChatCompletionClient,
    backend: ExecutionBackend,
    store: EventStore,
    context: tuple[dict[str, Any], ...] = (),
    control: RunControl | None = None,
    run_meta: dict[str, Any] | None = None,
) -> RunReport:
    control = control or RunControl()
    state = RunState(max_messages=config.max_messages, max_tokens=config.max_tokens)
    store.append(
        EventType.RUN_STARTED,
        "app",
        {
            "question": question,
            "mode": config.mode,
            "max_messages": config.max_messages,
            "max_tokens": config.max_tokens,
            "timeout_seconds": config.timeout_seconds,
            **(run_meta or {}),
        },
    )
    built = build_team(
        config.mode,
        clients=clients,
        selector_client=selector_client,
        backend=backend,
        store=store,
        state=state,
        run_id=store.run_id,
        require_results=config.require_results,
        completion_ceiling=config.completion_ceiling,
        fault=config.fault,
    )
    built.mapper.announce_first_speaker()

    def on_deadline() -> None:
        control.reason = control.reason or RunOutcome.TIMEOUT
        control.token.cancel()

    timer = asyncio.get_running_loop().call_later(config.timeout_seconds, on_deadline)
    result: TaskResult | None = None
    error: str | None = None
    try:
        async for item in built.team.run_stream(
            task=build_task(question, profile, context), cancellation_token=control.token
        ):
            if isinstance(item, TaskResult):
                result = item
    except asyncio.CancelledError:
        if control.reason is None:
            raise  # the surrounding task was cancelled, not this run's control
        state.finish(control.reason, "run cancelled")
    except Exception as exc:
        if state.token_blocked:  # a model call was refused by the token budget: not a fault
            log.warning("token budget exhausted: %s", state.outcome_detail)
        else:
            log.exception("run failed")
            error = f"{type(exc).__name__}: {exc}"[:500]
    finally:
        timer.cancel()
    outcome = built.mapper.finish(result, error)
    return RunReport(outcome, state)

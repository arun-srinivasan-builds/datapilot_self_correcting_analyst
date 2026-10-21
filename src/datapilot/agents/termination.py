"""App-owned run state, 12-message accounting and termination (PRP §3.2).

`RunState` is the single source of truth for: the agent-message counter, the last execution result,
token totals and the run outcome. The counter never resets. Observation is idempotent per message
id, so the termination condition (inside the team) and the event mapper see identical verdicts.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from autogen_agentchat.base import TerminationCondition
from autogen_agentchat.messages import BaseAgentEvent, BaseChatMessage, StopMessage

from datapilot.events.models import AGENTS, MAX_AGENT_MESSAGES

APPROVAL_TOKEN = "APPROVED"  # noqa: S105 - the Reviewer's approval keyword, not a credential


class RunOutcome(StrEnum):
    REVIEWER_APPROVED = "REVIEWER_APPROVED"
    LIMIT_REACHED = "LIMIT_REACHED"
    TOKEN_BUDGET_EXHAUSTED = "TOKEN_BUDGET_EXHAUSTED"  # noqa: S105
    TIMEOUT = "TIMEOUT"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class _Usage(Protocol):
    prompt_tokens: int
    completion_tokens: int


def is_standalone_approval(text: str) -> bool:
    """True only if the last non-empty line is exactly `APPROVED` and not inside a code fence.

    `NOT APPROVED`, `approved`, `APPROVED.` and an `APPROVED` line quoted in a fenced block do not
    qualify.
    """
    lines = text.rstrip().splitlines()
    if not lines or lines[-1].strip() != APPROVAL_TOKEN:
        return False
    return "\n".join(lines[:-1]).count("```") % 2 == 0


@dataclass(frozen=True, slots=True)
class ExecSummary:
    status: str
    exit_code: int | None


@dataclass(frozen=True, slots=True)
class MessageVerdict:
    counted: bool
    index: int = 0
    approved: bool = False
    approval_ignored: str | None = None
    outcome: RunOutcome | None = None


@dataclass
class RunState:
    max_messages: int = MAX_AGENT_MESSAGES
    max_tokens: int = 30_000
    agent_messages: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    last_exec: ExecSummary | None = None
    outcome: RunOutcome | None = None
    outcome_detail: str = ""
    token_blocked: bool = False
    usage_by_source: dict[str, list[int]] = field(default_factory=dict)
    injected_hashes: dict[str, str] = field(default_factory=dict)  # code hash -> test-only fault
    last_valid_result: Any = None  # last successful, contract-valid ExecutionResult
    last_valid_code_hash: str = ""
    sequence: list[str] = field(default_factory=list)
    _verdicts: dict[str, MessageVerdict] = field(default_factory=dict, repr=False)
    _exec_since_last_turn: bool = field(default=False, repr=False)
    _infra_error: str | None = field(default=None, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def last_exec_ok(self) -> bool:
        return self.last_exec is not None and self.last_exec.status == "ok"

    def begin_exec(self) -> None:
        with self._lock:
            self._exec_since_last_turn = True

    def record_exec(self, status: str, exit_code: int | None) -> None:
        with self._lock:
            self._exec_since_last_turn = True
            self.last_exec = ExecSummary(status, exit_code)

    def record_infra_error(self, detail: str) -> None:
        with self._lock:
            self._infra_error = detail

    def add_usage(self, prompt_tokens: int, completion_tokens: int, source: str = "run") -> None:
        """Record the model-reported usage of one model call (any role, selector included)."""
        with self._lock:
            self.input_tokens += prompt_tokens
            self.output_tokens += completion_tokens
            row = self.usage_by_source.setdefault(source, [0, 0, 0])
            row[0] += prompt_tokens
            row[1] += completion_tokens
            row[2] += 1

    def block_for_budget(self, estimate: int) -> None:
        """A model call was refused because it would exceed the token budget."""
        with self._lock:
            self.token_blocked = True
            self.finish(
                RunOutcome.TOKEN_BUDGET_EXHAUSTED,
                f"{self.total_tokens} of {self.max_tokens} tokens used; next prompt ~{estimate}",
            )

    def finish(self, outcome: RunOutcome, detail: str = "") -> bool:
        """Set the outcome unless one exists already (first outcome wins)."""
        with self._lock:
            if self.outcome is not None:
                return False
            self.outcome, self.outcome_detail = outcome, detail
            return True

    def observe(
        self, message_id: str, source: str, content: str, usage: _Usage | None
    ) -> MessageVerdict:
        """Account for one chat message. Idempotent per `message_id`."""
        with self._lock:
            if message_id in self._verdicts:
                return self._verdicts[message_id]
            verdict = self._observe(source, content, usage)
            self._verdicts[message_id] = verdict
            return verdict

    def _observe(self, source: str, content: str, usage: _Usage | None) -> MessageVerdict:
        # Task message, human stage, anything else: never counted. After the outcome is set, a
        # late message is not counted either, so a 13th message can never enter the budget.
        if source not in AGENTS or self.outcome is not None:
            return MessageVerdict(counted=False)
        self.agent_messages += 1
        index = self.agent_messages
        self.sequence.append(source)
        # Token usage is accounted per model call by `BudgetedClient` (it also covers selector
        # calls); `usage` here is only descriptive and must not be added a second time.
        if source == "Executor":
            if not self._exec_since_last_turn:  # e.g. "No code blocks found": nothing ran
                self.last_exec = ExecSummary("not_executed", None)
            self._exec_since_last_turn = False
            if self._infra_error is not None:
                self.finish(RunOutcome.ERROR, self._infra_error)
        approved, ignored = False, None
        if source == "Reviewer" and is_standalone_approval(content):
            if self.last_exec_ok:
                approved = True
                self.finish(RunOutcome.REVIEWER_APPROVED)
            else:
                ignored = "last_execution_failed"
        if self.outcome is None and index >= self.max_messages:
            self.finish(RunOutcome.LIMIT_REACHED, f"{index} agent messages")
        if self.outcome is None and self.total_tokens >= self.max_tokens:
            self.finish(RunOutcome.TOKEN_BUDGET_EXHAUSTED, f"{self.total_tokens} tokens")
        return MessageVerdict(
            counted=True,
            index=index,
            approved=approved,
            approval_ignored=ignored,
            outcome=self.outcome,
        )


def message_text(message: BaseAgentEvent | BaseChatMessage) -> str:
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else str(content)


class RunTerminator(TerminationCondition):
    """Single termination condition. Evaluated for every message the team delivers.

    `on_message` (optional) is invoked first for each chat message so that events are recorded in
    exactly the order the team processed them, before the next speaker is selected.
    """

    def __init__(self, state: RunState, on_message: _OnMessage | None = None) -> None:
        self._state = state
        self._on_message = on_message

    @property
    def terminated(self) -> bool:
        return self._state.outcome is not None

    async def __call__(
        self, messages: Sequence[BaseAgentEvent | BaseChatMessage]
    ) -> StopMessage | None:
        for message in messages:
            if not isinstance(message, BaseChatMessage):
                continue
            if self._on_message is not None:
                self._on_message(message)
            else:
                self._state.observe(
                    message.id, message.source, message_text(message), message.models_usage
                )
            if self._state.outcome is not None:
                return StopMessage(content=self._state.outcome.value, source="RunTerminator")
        return None

    async def reset(self) -> None:
        """Deliberately a no-op: the counter never resets within a run (a new run = a new state)."""


class _OnMessage(Protocol):
    def __call__(self, message: BaseChatMessage) -> None: ...

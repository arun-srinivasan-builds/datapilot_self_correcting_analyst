"""Normalized, immutable runtime events. One event per real occurrence; none are synthesized."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

AGENTS: tuple[str, ...] = ("Planner", "Coder", "Executor", "Reviewer")
MAX_AGENT_MESSAGES = 12


class EventType(StrEnum):
    RUN_STARTED = "run_started"
    SPEAKER_SELECTED = "speaker_selected"
    AGENT_MESSAGE = "agent_message"
    CODE_GENERATED = "code_generated"
    EXEC_STARTED = "exec_started"
    EXEC_RESULT = "exec_result"
    REPAIR_ROUTED = "repair_routed"
    REVIEW_FEEDBACK = "review_feedback"
    REVIEWER_APPROVED = "reviewer_approved"
    LIMIT_REACHED = "limit_reached"
    TERMINATED = "terminated"
    RUN_ERROR = "run_error"
    GUARDRAIL = "guardrail"
    USAGE = "usage"
    HUMAN_APPROVED = "human_approved"
    HUMAN_REJECTED = "human_rejected"
    HUMAN_FOLLOW_UP = "human_follow_up"
    TEST_FAULT_INJECTED = "test_fault_injected"


TERMINAL_TYPES = frozenset(
    {EventType.REVIEWER_APPROVED, EventType.LIMIT_REACHED, EventType.RUN_ERROR}
)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, list | tuple | set | frozenset):
        return tuple(_freeze(v) for v in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    return value


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    seq: int
    run_id: str
    ts: datetime
    type: EventType
    source: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("RuntimeEvent.source is required: no event without a real source")
        object.__setattr__(self, "payload", _freeze(dict(self.payload)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "run_id": self.run_id,
            "ts": self.ts.astimezone(UTC).isoformat(timespec="milliseconds"),
            "type": self.type.value,
            "source": self.source,
            "payload": _thaw(self.payload),
        }

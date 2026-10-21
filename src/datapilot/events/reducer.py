"""Pure reducer: events -> CanvasState. The Livewire renders only from this state."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Literal

from datapilot.events.models import (
    AGENTS,
    MAX_AGENT_MESSAGES,
    TERMINAL_TYPES,
    EventType,
    RuntimeEvent,
)

Phase = Literal["idle", "running", "approved", "limit_reached", "error"]
NodeStatus = Literal["idle", "active", "done", "ok", "error", "feedback", "approved"]
HumanStatus = Literal["none", "pending", "approved", "rejected", "follow_up"]


def _idle_nodes() -> dict[str, NodeStatus]:
    return {a: "idle" for a in AGENTS}


@dataclass(frozen=True, slots=True)
class CanvasState:
    run_id: str | None = None
    phase: Phase = "idle"
    message_count: int = 0
    max_messages: int = MAX_AGENT_MESSAGES
    active_agent: str | None = None
    nodes: dict[str, NodeStatus] = field(default_factory=_idle_nodes)
    repair_attempts: int = 0
    feedback_rounds: int = 0
    last_exec_ok: bool | None = None
    fault_injected: bool = False
    human: HumanStatus = "none"
    input_tokens: int = 0
    output_tokens: int = 0
    violations: tuple[str, ...] = ()
    last_seq: int = 0

    @property
    def is_terminal(self) -> bool:
        return self.phase in ("approved", "limit_reached", "error")

    @property
    def reviewer_verified(self) -> bool:
        return self.phase == "approved"

    @property
    def fully_verified(self) -> bool:
        """Reviewer approval AND a separate human approval."""
        return self.phase == "approved" and self.human == "approved"


def _node(state: CanvasState, agent: str, status: NodeStatus) -> dict[str, NodeStatus]:
    return {**state.nodes, agent: status}


def _activate(state: CanvasState, agent: str) -> dict[str, NodeStatus]:
    """Only one node is `active` at a time; a previously active node becomes `done`."""
    nodes = dict(state.nodes)
    for name, status in nodes.items():
        if status == "active":
            nodes[name] = "done"
    nodes[agent] = "active"
    return nodes


def apply_event(state: CanvasState, ev: RuntimeEvent) -> CanvasState:
    t, p = ev.type, ev.payload
    s = replace(state, last_seq=ev.seq, run_id=state.run_id or ev.run_id)

    def violate(code: str) -> CanvasState:
        return replace(s, violations=(*s.violations, f"{code}@{ev.seq}"))

    if t in TERMINAL_TYPES and s.is_terminal:
        return violate("second_terminal_event")

    if t is EventType.RUN_STARTED:
        return replace(s, phase="running", nodes=_idle_nodes())
    if t is EventType.SPEAKER_SELECTED:
        nxt = str(p.get("next", ""))
        return (
            replace(s, active_agent=nxt, nodes=_activate(s, nxt))
            if nxt in AGENTS
            else violate("unknown_speaker")
        )
    if t is EventType.AGENT_MESSAGE:
        if ev.source not in AGENTS:
            return violate("message_from_non_agent")
        if s.is_terminal:
            return violate("message_after_terminal")
        count = s.message_count + 1
        # a chat message must not erase the real result status (error/ok/feedback/approved)
        keep = s.nodes.get(ev.source) in ("error", "ok", "feedback", "approved")
        nodes = s.nodes if keep else _node(s, ev.source, "done")
        out = replace(s, message_count=count, active_agent=ev.source, nodes=nodes)
        return (
            replace(out, violations=(*out.violations, f"cap_exceeded@{ev.seq}"))
            if (count > s.max_messages)
            else out
        )
    if t is EventType.EXEC_STARTED:
        return replace(s, active_agent="Executor", nodes=_activate(s, "Executor"))
    if t is EventType.EXEC_RESULT:
        ok = p.get("status") == "ok"
        return replace(s, last_exec_ok=ok, nodes=_node(s, "Executor", "ok" if ok else "error"))
    if t is EventType.REPAIR_ROUTED:
        return replace(s, repair_attempts=s.repair_attempts + 1, nodes=_activate(s, "Coder"))
    if t is EventType.REVIEW_FEEDBACK:
        return replace(
            s, feedback_rounds=s.feedback_rounds + 1, nodes=_node(s, "Reviewer", "feedback")
        )
    if t is EventType.REVIEWER_APPROVED:
        if ev.source != "Reviewer" or s.last_exec_ok is not True:
            return violate("invalid_approval")
        return replace(
            s, phase="approved", active_agent=None, nodes=_node(s, "Reviewer", "approved")
        )
    if t is EventType.LIMIT_REACHED:
        return replace(s, phase="limit_reached", active_agent=None)
    if t is EventType.RUN_ERROR:
        return replace(s, phase="error", active_agent=None)
    if t is EventType.TEST_FAULT_INJECTED:
        return replace(s, fault_injected=True)
    if t is EventType.USAGE:
        return replace(
            s,
            input_tokens=s.input_tokens + int(p.get("input_tokens", 0)),
            output_tokens=s.output_tokens + int(p.get("output_tokens", 0)),
        )
    if t in (EventType.HUMAN_APPROVED, EventType.HUMAN_REJECTED, EventType.HUMAN_FOLLOW_UP):
        if not s.is_terminal:
            return violate("human_decision_before_terminal")
        decided = s.human in ("approved", "rejected")
        if t is EventType.HUMAN_FOLLOW_UP:
            # a follow-up question never overwrites an earlier approval/rejection
            return s if decided else replace(s, human="follow_up")
        if decided:
            return violate("duplicate_human_decision")
        if t is EventType.HUMAN_APPROVED:
            if s.phase != "approved":  # Reviewer approval is a precondition of human approval
                return violate("human_approval_without_reviewer_approval")
            return replace(s, human="approved")
        return replace(s, human="rejected")
    # CODE_GENERATED, TERMINATED, GUARDRAIL: recorded in the log; no canvas state change.
    return s


def reduce_events(events: Iterable[RuntimeEvent]) -> CanvasState:
    state = CanvasState()
    for ev in events:
        state = apply_event(state, ev)
    return state

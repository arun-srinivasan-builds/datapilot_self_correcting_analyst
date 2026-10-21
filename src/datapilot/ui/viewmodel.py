"""Pure view-model: RuntimeEvents + CanvasState -> what the Livewire shows.

Everything the canvas displays is derived from the event list (no timers, no invented progress).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from datapilot.events import AGENTS, CanvasState, EventType, RuntimeEvent, reduce_events

NODE_ORDER = (*AGENTS, "Human")
NODE_SUB = {
    "Planner": "plans",
    "Coder": "writes / repairs code",
    "Executor": "runs in sandbox",
    "Reviewer": "checks · only approver",
    "Human": "approval stage",
}


@dataclass(frozen=True)
class NodeView:
    status: str  # css class suffix: idle waiting active done ok error feedback approved pending terminal
    label: str


@dataclass(frozen=True)
class Canvas:
    state: CanvasState
    nodes: dict[str, NodeView]
    edges: dict[str, str]
    fault: bool
    events: tuple[RuntimeEvent, ...]


def _last(events: Sequence[RuntimeEvent], *types: EventType) -> RuntimeEvent | None:
    for ev in reversed(events):
        if ev.type in types:
            return ev
    return None


def build_canvas(events: Sequence[RuntimeEvent]) -> Canvas:
    state = reduce_events(events)
    started = any(e.type is EventType.RUN_STARTED for e in events)
    last_type = events[-1].type if events else None
    last_exec = _last(events, EventType.EXEC_RESULT)
    last_fb = _last(events, EventType.REVIEW_FEEDBACK)
    code = _last(events, EventType.CODE_GENERATED)
    exit_code = int(last_exec.payload.get("exit_code", 1)) if last_exec else 1
    nodes: dict[str, NodeView] = {}

    for name in AGENTS:
        status = state.nodes.get(name, "idle")
        if not started:
            nodes[name] = NodeView("idle", "IDLE")
            continue
        label = {
            "idle": "WAITING",
            "done": "DONE",
            "active": "ACTIVE",
            "ok": "OK",
            "error": "ERROR",
            "feedback": "FEEDBACK",
            "approved": "APPROVED",
        }[status]
        css = "waiting" if status == "idle" else status
        if name == "Planner" and status == "active":
            label = "PLANNING"
        if name == "Coder" and status == "active":
            if (
                state.repair_attempts
                and last_type in (EventType.REPAIR_ROUTED, EventType.SPEAKER_SELECTED)
                and state.last_exec_ok is False
            ):
                label = f"REPAIRING · ATTEMPT {state.repair_attempts}"
            elif state.feedback_rounds and state.last_exec_ok:
                label = "REVISING"
            else:
                label = "WRITING CODE"
        if name == "Executor":
            if status == "ok":
                label = "OK · EXIT 0"
            elif status == "error":
                label = f"ERROR · EXIT {exit_code}"
            elif status == "active":
                label = "RUNNING"
        if name == "Reviewer":
            if status == "feedback":
                issues = int(last_fb.payload.get("issues", 0)) if last_fb else 0
                label = f"FEEDBACK · {issues} ISSUES" if issues else "FEEDBACK"
                if state.phase == "limit_reached":
                    label = "NEVER APPROVED"
            elif status == "approved":
                label = f"APPROVED · MSG {state.message_count}"
        nodes[name] = NodeView(css, label)

    # Human stage is separate from Reviewer approval
    if not started:
        nodes["Human"] = NodeView("idle", "NOT STARTED")
    elif state.human == "approved":
        nodes["Human"] = NodeView("approved", "APPROVED BY HUMAN")
    elif state.human == "rejected":
        nodes["Human"] = NodeView("terminal", "REJECTED BY HUMAN")
    elif state.human == "follow_up":
        nodes["Human"] = NodeView("pending", "FOLLOW-UP REQUESTED")
    elif state.phase == "approved":
        nodes["Human"] = NodeView("pending", "PENDING DECISION")
    elif state.phase == "limit_reached":
        nodes["Human"] = NodeView("terminal", "RUN UNAPPROVED")
    elif state.phase == "error":
        nodes["Human"] = NodeView("terminal", "RUN FAILED")
    else:
        nodes["Human"] = NodeView("waiting", "AFTER REVIEW")

    types = {e.type for e in events}
    edges: dict[str, str] = {}
    if code or state.active_agent in ("Coder", "Executor", "Reviewer"):
        edges["p_c"] = "used"
    if EventType.EXEC_STARTED in types:
        edges["c_e"] = "done-ok" if state.last_exec_ok else "used"
    if (
        state.nodes.get("Reviewer") in ("feedback", "approved")
        or EventType.REVIEW_FEEDBACK in types
    ):
        edges["e_r"] = "done-ok" if state.phase == "approved" else "used"
    if state.repair_attempts:
        edges["repair"] = "used"
    if state.feedback_rounds:
        edges["feedback"] = "used"
    # one animation per real transfer: only the most recent routing event animates
    if state.phase == "approved":
        edges["r_h"] = "flow"
    elif last_type is EventType.REPAIR_ROUTED or (
        last_type is EventType.SPEAKER_SELECTED
        and state.nodes.get("Executor") == "error"
        and state.active_agent == "Coder"
    ):
        edges["repair"] = "repair"
    elif (
        last_type is EventType.SPEAKER_SELECTED
        and state.nodes.get("Reviewer") == "feedback"
        and state.active_agent == "Coder"
    ):
        edges["feedback"] = "feedback"
    elif last_type is EventType.REVIEW_FEEDBACK:
        edges["feedback"] = "feedback"

    return Canvas(state, nodes, edges, state.fault_injected, tuple(events))


@dataclass(frozen=True)
class LedgerRow:
    index: int
    agent: str
    event: str
    outcome: str
    tone: str


def ledger_rows(events: Sequence[RuntimeEvent]) -> list[LedgerRow]:
    """One row per counted agent message, straight from the event log."""
    rows: list[LedgerRow] = []
    for ev in events:
        if ev.type is EventType.AGENT_MESSAGE and ev.source in AGENTS:
            rows.append(
                LedgerRow(
                    len(rows) + 1,
                    ev.source,
                    str(ev.payload.get("event", "agent_message")),
                    str(ev.payload.get("outcome", "")),
                    str(ev.payload.get("tone", "")),
                )
            )
    return rows


@dataclass(frozen=True)
class FeedItem:
    marker: str
    who: str
    text: str
    cls: str


def feed_items(events: Sequence[RuntimeEvent], limit: int = 8) -> list[FeedItem]:
    """Newest-last feed of runtime events; counted agent messages carry their 1-based number."""
    items: list[FeedItem] = []
    n = 0
    for ev in events:
        t, p = ev.type, ev.payload
        if t is EventType.AGENT_MESSAGE and ev.source in AGENTS:
            n += 1
            tone = str(p.get("tone", ""))
            cls = {"bad": "err", "warn": "fb", "ok": "ok"}.get(tone, "")
            items.append(
                FeedItem(str(n), ev.source, f"{p.get('event', '')} · {p.get('outcome', '')}", cls)
            )
        elif t is EventType.RUN_STARTED:
            items.append(FeedItem("•", "app", "run_started · question + dataset fingerprint", "ev"))
        elif t is EventType.SPEAKER_SELECTED:
            items.append(FeedItem("•", "selector", f"speaker_selected → {p.get('next', '')}", "ev"))
        elif t is EventType.REPAIR_ROUTED:
            items.append(
                FeedItem(
                    "•",
                    "app",
                    f"repair_routed · Executor → Coder · attempt {p.get('attempt', 1)}",
                    "ev",
                )
            )
        elif t is EventType.TEST_FAULT_INJECTED:
            items.append(
                FeedItem(
                    "•", ev.source, f"test_fault_injected · {p.get('detail', '')} (TEST ONLY)", "ev"
                )
            )
        elif t is EventType.REVIEWER_APPROVED:
            items.append(FeedItem("•", "app", "reviewer_approved", "ev"))
        elif t is EventType.LIMIT_REACHED:
            items.append(FeedItem("•", "app", f"limit_reached · count {p.get('count', 12)}", "ev"))
        elif t is EventType.TERMINATED:
            items.append(FeedItem("•", "app", f"terminated · {p.get('reason', '')}", "ev"))
        elif t in (EventType.HUMAN_APPROVED, EventType.HUMAN_REJECTED, EventType.HUMAN_FOLLOW_UP):
            items.append(FeedItem("•", "human", t.value, "ev"))
    return items[-limit:]

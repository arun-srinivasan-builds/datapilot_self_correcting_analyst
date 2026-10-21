"""Agent Livewire: renders strictly from RuntimeEvents via the reducer.

Until M3 the only event source is a scripted, clearly labelled design preview; with no preview
selected the canvas shows the genuine idle state. Nothing animates without an event.
"""

from __future__ import annotations

from html import escape

import streamlit as st

from datapilot.events import EventType, RuntimeEvent
from datapilot.ui import markup as h
from datapilot.ui.chrome import common_chips
from datapilot.ui.live import get_live
from datapilot.ui.preview import SCENARIO_ORDER, SCENARIOS, events_for
from datapilot.ui.viewmodel import Canvas, build_canvas, feed_items, ledger_rows

LABELS = {k: SCENARIOS[k][0] for k in SCENARIO_ORDER}


INSPECTOR_TABS = ["Plan", "Code", "Output / stderr", "Reviewer", "Tokens"]
INSPECTOR_DEFAULT = {
    "running": "Plan",
    "exec-error": "Output / stderr",
    "repair": "Code",
    "reviewer-feedback": "Reviewer",
    "approved": "Reviewer",
    "limit-reached": "Output / stderr",
    "fault-injection": "Output / stderr",
}


def _pick() -> None:
    key = st.session_state.get("preview_pick")
    st.session_state["preview_key"] = key
    st.session_state["human"] = None
    st.session_state["inspector"] = INSPECTOR_DEFAULT.get(key, "Plan")


def _last(events: tuple[RuntimeEvent, ...], *types: EventType) -> RuntimeEvent | None:
    for ev in reversed(events):
        if ev.type in types:
            return ev
    return None


LIMIT_TEXT = {
    "LIMIT_REACHED": (
        "Stopped at {n}/12 — not approved by the Reviewer",
        "Ask a follow-up (new run, fresh budget) or inspect the partial work.",
    ),
    "TOKEN_BUDGET_EXHAUSTED": (
        "Token budget exhausted after {n} messages — not approved",
        "The run stopped before the Reviewer could approve. Raise MAX_RUN_TOKENS or ask a narrower question.",
    ),
    "TIMEOUT": (
        "Wall-clock limit reached after {n} messages — not approved",
        "The run exceeded RUN_TIMEOUT_SECONDS and was cancelled.",
    ),
    "STOPPED": (
        "Stopped by you after {n} messages — not approved",
        "The run was cancelled; no result is verified.",
    ),
}


def outcome(canvas: Canvas) -> tuple[str, str, str]:
    s = canvas.state
    if canvas.fault and s.phase == "running":
        return (
            "bad",
            "TEST FAULT INJECTED — not a natural error",
            "The Coder is repairing from the real stderr. This run is labelled test-only everywhere.",
        )
    if s.phase == "idle":
        return ("", "No run", "Submit a question in Ask & Explore to start a real run.")
    if s.phase == "approved":
        return (
            "ok",
            f"Reviewer approved on message {s.message_count} of 12",
            "Human approval is a separate step in Insights Studio. Nothing is final until you decide.",
        )
    if s.phase == "limit_reached":
        ev = _last(canvas.events, EventType.LIMIT_REACHED)
        reason = str(ev.payload.get("reason", "LIMIT_REACHED")) if ev else "LIMIT_REACHED"
        title, body = LIMIT_TEXT.get(reason, LIMIT_TEXT["LIMIT_REACHED"])
        return ("bad", title.format(n=s.message_count), body)
    if s.phase == "error":
        ev = _last(canvas.events, EventType.RUN_ERROR)
        detail = str(ev.payload.get("reason", "error")) if ev else "error"
        return ("bad", "Run failed — not approved", detail[:300])
    if s.nodes.get("Executor") == "error" and s.active_agent == "Coder":
        return (
            "run",
            "Coder is repairing from the real error",
            "The Executor's stderr was returned verbatim to the Coder.",
        )
    if s.nodes.get("Reviewer") == "feedback":
        return (
            "run",
            "Reviewer returned feedback to the Coder",
            "The Reviewer cannot approve this revision; the Coder must fix and re-execute.",
        )
    return ("run", "Run in progress", "The counter counts only real agent messages.")


def _tokens_label(events: tuple[RuntimeEvent, ...]) -> str:
    total = sum(
        int(e.payload.get("input_tokens", 0)) + int(e.payload.get("output_tokens", 0))
        for e in events
        if e.type is EventType.USAGE
    )
    return f"{total:,} tokens" if total else "— (no calls yet)"


def render() -> None:
    """Live runs poll the real EventStore once a second; the fragment stops itself when it ends."""
    live = get_live()
    running = live.running
    st.session_state["lw_was_running"] = running
    st.fragment(run_every=1.0 if running else None)(_body)()


def _body() -> None:
    live = get_live()
    loaded = st.session_state.get("loaded")
    is_live = live.current_run_id is not None
    key = None if is_live else st.session_state.get("preview_key")
    events = live.events() if is_live else events_for(key, st.session_state.get("human"))
    if st.session_state.get("lw_was_running") and not live.running:
        live.latest_view()  # collect the finished run, then refresh every workspace once
        st.session_state["lw_was_running"] = False
        st.rerun()
    canvas = build_canvas(events)
    s = canvas.state
    rows = ledger_rows(events)

    run_chip = {
        "idle": h.chip("Idle", ""),
        "running": h.chip("Running", "live"),
        "approved": h.chip(f"Reviewer approved · {s.message_count}/12", "ok"),
        "limit_reached": h.chip(
            "Unapproved · limit 12/12"
            if s.message_count >= 12
            else f"Unapproved · stopped {s.message_count}/12",
            "bad",
        ),
        "error": h.chip("Run failed", "bad"),
    }[s.phase]
    if s.phase == "running" and s.repair_attempts and s.nodes.get("Executor") == "error":
        run_chip = h.chip(f"Repairing · attempt {s.repair_attempts}", "warn")
    chips = [*common_chips(loaded), run_chip]
    chips.append(h.counter(s.message_count, [r.tone for r in rows]))
    st.markdown(h.toolbar("Agent Livewire", chips), unsafe_allow_html=True)
    if live.running:
        st.button("Stop run", key="stop-run", on_click=live.stop, help="Cancels the real run.")
    if live.error:
        st.error(f"The run failed to start: {live.error}")
    if key is not None:
        st.markdown(
            h.banner(
                "Scripted illustrative sequence rendered through the real event model. Not a live run, "
                "not AI output. Real runs arrive in M3."
            ),
            unsafe_allow_html=True,
        )

    if not is_live:
        with st.container(key="preview-bar"):
            st.segmented_control(
                "Design preview state (review aid)",
                list(SCENARIO_ORDER),
                format_func=LABELS.get,
                key="preview_pick",
                default=key,
                on_change=_pick,
                help="Clear the selection to see the genuine idle state.",
            )
    started = next((e for e in events if e.type is EventType.RUN_STARTED), None)
    if started is not None:
        mode = "Round-robin" if started.payload.get("mode") == "round_robin" else "Guarded selector"
    else:
        mode = "Guarded selector" if key else "no run"
    st.markdown(
        '<div class="dp-grid" style="padding-bottom:0"><div class="dp-pane" aria-label="Agent workflow">'
        + h.pane_header(f"Agent workflow · {mode}", "Every motion = one real event")
        + h.LEGEND
        + h.flow_svg(canvas)
        + "</div></div>",
        unsafe_allow_html=True,
    )

    feed_col, insp_col, facts_col = st.columns([1.2, 3.0, 1.1])
    with feed_col, st.container(key="pane-feed"):
        st.markdown(h.pane_header("Live feed · runtime events"), unsafe_allow_html=True)
        st.markdown(
            '<div class="flush">' + h.feed_html(feed_items(events)) + "</div>",
            unsafe_allow_html=True,
        )

    with insp_col, st.container(key="pane-inspector"):
        st.markdown(
            h.pane_header("Inspector · evidence from the event log"), unsafe_allow_html=True
        )
        tab = (
            st.segmented_control(
                "Inspector view",
                INSPECTOR_TABS,
                key="inspector",
                default=INSPECTOR_DEFAULT.get(key, "Plan"),
                label_visibility="collapsed",
            )
            or "Plan"
        )
        if tab == "Plan":
            plan = next((e for e in reversed(events) if e.payload.get("plan")), None)
            st.markdown(
                h.text_block(str(plan.payload["plan"]))
                if plan
                else '<div class="muted">No plan yet.</div>',
                unsafe_allow_html=True,
            )
        elif tab == "Code":
            code = _last(events, EventType.CODE_GENERATED)
            st.markdown(
                h.code_block(
                    str(code.payload["code"]),
                    int(code.payload.get("mark_line", 0)),
                    str(code.payload.get("mark_kind", "")),
                )
                if code
                else '<div class="muted">No code generated yet.</div>',
                unsafe_allow_html=True,
            )
        elif tab == "Output / stderr":
            res = _last(events, EventType.EXEC_RESULT)
            if res is None:
                st.markdown('<div class="muted">No execution yet.</div>', unsafe_allow_html=True)
            elif res.payload.get("status") == "ok":
                out = str(res.payload.get("stdout") or "Executed successfully (exit 0).")
                st.markdown(h.text_block(out, "okc"), unsafe_allow_html=True)
            else:
                st.markdown(h.err_block(str(res.payload.get("stderr", ""))), unsafe_allow_html=True)
        elif tab == "Reviewer":
            fb = _last(events, EventType.REVIEW_FEEDBACK, EventType.REVIEWER_APPROVED)
            if fb is None:
                st.markdown(
                    '<div class="muted">No Reviewer verdict yet.</div>', unsafe_allow_html=True
                )
            else:
                cls = "okc" if fb.type is EventType.REVIEWER_APPROVED else "fb"
                st.markdown(
                    h.text_block(str(fb.payload.get("text", "")), cls), unsafe_allow_html=True
                )
        elif is_live:
            usage = [e for e in events if e.type is EventType.USAGE]
            if not usage:
                st.markdown('<div class="muted">No model call yet.</div>', unsafe_allow_html=True)
            else:
                per: dict[str, list[int]] = {}
                for e in usage:
                    row = per.setdefault(e.source, [0, 0, 0])
                    row[0] += int(e.payload.get("input_tokens", 0))
                    row[1] += int(e.payload.get("output_tokens", 0))
                    row[2] += 1
                st.markdown(
                    h.table(
                        ["Source", "Calls", "Input", "Output"],
                        [[escape(k), str(v[2]), f"{v[0]:,}", f"{v[1]:,}"] for k, v in per.items()],
                        right=(1, 2, 3),
                    ),
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div class="muted">Design preview: no model calls, so no figures are shown.</div>',
                unsafe_allow_html=True,
            )

    with facts_col, st.container(key="pane-facts"):
        kind, title, body = outcome(canvas)
        reviewer = {"approved": "Approved", "limit_reached": "Unapproved"}.get(s.phase, "Pending")
        human = {
            "none": "—",
            "approved": "Approved",
            "rejected": "Rejected",
            "follow_up": "Follow-up",
        }[s.human]
        if s.phase == "approved" and s.human == "none":
            human = "Pending"
        st.markdown(h.pane_header("Run facts"), unsafe_allow_html=True)
        st.markdown(
            h.outcome_html(kind, title, body).replace(
                "margin:var(--pad) var(--pad) 0", "margin:0 0 12px"
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            h.facts_html(
                canvas, reviewer, human, _tokens_label(events) if is_live else "— (not recorded)"
            ).replace("padding:var(--pad)", "padding:0"),
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="muted" style="margin-top:8px">Cost: Pricing not configured</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div style="padding:var(--gap) var(--pad) 0">' + h.ledger_html(rows) + "</div>",
        unsafe_allow_html=True,
    )

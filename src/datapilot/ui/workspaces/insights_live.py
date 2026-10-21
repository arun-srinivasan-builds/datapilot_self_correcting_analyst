"""Insights Studio for a REAL finished run: facts, charts and exports come from its results.json.

Everything shown is read from the run's validated artifacts and event log. Agent-written text is
untrusted and always escaped. Exports exist only for Reviewer-approved runs.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

import streamlit as st

from datapilot.events import EventType, reduce_events
from datapilot.reports.pdf import ChartImage, build_pdf
from datapilot.ui import markup as h
from datapilot.ui.chrome import common_chips
from datapilot.ui.live import LiveSession, RunView, results_payload

_REASONS = {
    "LIMIT_REACHED": "12-message limit reached",
    "TOKEN_BUDGET_EXHAUSTED": "token budget exhausted",
    "TIMEOUT": "wall-clock limit reached",
    "STOPPED": "stopped by the user",
    "ERROR": "run error",
}


def _fmt(value: Any, unit: str = "") -> str:
    if isinstance(value, bool) or not isinstance(value, int | float):
        text = str(value)
    elif float(value).is_integer() or abs(value) >= 1000:
        text = f"{value:,.0f}"
    else:
        text = f"{value:,.2f}"
    return f"{text} {unit}".strip() if unit else text


def _human_label(view: RunView) -> str:
    return {"none": "Pending", "approved": "Approved", "rejected": "Rejected"}.get(
        view.record.human_status, view.record.human_status
    )


def analysis_script(view: RunView) -> str:
    rec = view.record
    header = (
        '"""DataPilot export - the exact script the Executor ran and the Reviewer approved.\n\n'
        f"run {rec.run_id} - code hash {rec.code_hash}\n"
        f"question: {rec.question[:200]!r}\n"
        "Usage: set DATA_PATH to the dataset file and OUTPUT_DIR to an existing folder, then run.\n"
        '"""\n'
    )
    return header + view.code


@st.cache_data(show_spinner=False, max_entries=8)
def _pdf(key: str, payload: dict[str, Any]) -> bytes:
    del key  # cache key only
    return build_pdf(**payload)


def _trail(view: RunView) -> list[tuple[str, str]]:
    """Verification flags derived from real events only."""
    flags: list[tuple[str, str]] = []
    n_exec = 0
    for e in view.events:
        if e.type is EventType.EXEC_RESULT:
            n_exec += 1
            if e.payload.get("status") == "ok":
                flags.append(("ok", f"Execution {n_exec} exit 0"))
            else:
                err = str(e.payload.get("stderr", "")).strip().splitlines()
                last = escape(err[-1][:140]) if err else "error"
                note = " (test-injected fault)" if e.payload.get("injected_fault") else ""
                flags.append(("bad", f"Execution {n_exec} failed{note}: {last} → Coder repaired"))
        elif e.type is EventType.REVIEW_FEEDBACK:
            flags.append(
                ("warn", f"Reviewer asked for changes ({e.payload.get('issues', '?')} issues)")
            )
        elif e.type is EventType.REVIEWER_APPROVED:
            flags.append(("ok", f"Reviewer APPROVED (message {e.payload.get('message', '?')}/12)"))
    return flags


def render_live(live: LiveSession, view: RunView) -> None:
    rec = view.record
    canvas = reduce_events(view.events)
    chips = common_chips(st.session_state.get("loaded"))
    approved = rec.reviewer_approved
    chips.append(
        h.chip(f"Reviewer: Approved · {rec.messages}/12", "ok")
        if approved
        else h.chip(f"Reviewer: Unapproved · {rec.messages}/12", "bad")
    )
    chips.append(
        h.chip(f"Human: {_human_label(view)}", "ok" if rec.human_status == "approved" else "info")
    )
    st.markdown(h.toolbar("Insights Studio", chips), unsafe_allow_html=True)

    if not approved:
        reason = _REASONS.get(rec.outcome.value, rec.outcome.value)
        st.markdown(
            h.banner(
                f"UNAPPROVED — {reason}. No verified result and no exports for this run "
                "(r{}). Inspect the partial work in Agent Livewire or ask again.".format(
                    rec.sequence
                )
            ),
            unsafe_allow_html=True,
        )
        _follow_up(live, view, label="Ask again")
        return

    data = results_payload(view)
    facts = [f for f in data.get("answer_facts", []) if isinstance(f, dict)]
    charts = [c for c in data.get("charts", []) if isinstance(c, dict)]
    lead = [f for f in facts if not isinstance(f.get("value"), int | float)][:3] or facts[:3]
    headline = "<br>".join(
        f'<span style="font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;'
        f'color:var(--muted)">{escape(str(f["label"])[:80])}</span> '
        f"{escape(_fmt(f['value'], str(f.get('unit', ''))))}"
        for f in lead
    )
    status_chip = h.chip(f"Reviewer approved · msg {rec.messages}/12", "ok")
    st.markdown(
        f'<div class="report"><div class="q"><b>Question</b> · {escape(rec.question)}</div>'
        f'<p class="answer">{headline}</p>{status_chip} '
        f"{h.chip('Human: ' + _human_label(view), 'info')}</div>",
        unsafe_allow_html=True,
    )
    numeric = [f for f in facts if isinstance(f.get("value"), int | float)][:5]
    if numeric:
        st.markdown(
            h.strip(
                [
                    (
                        str(f["label"])[:90],
                        escape(_fmt(f["value"], "")),
                        escape(str(f.get("unit", ""))[:30]),
                    )
                    for f in numeric
                ]
            ),
            unsafe_allow_html=True,
        )

    if charts:
        cols = st.columns(min(2, len(charts)))
        for i, chart in enumerate(charts):
            png = view.artifacts.get(str(chart.get("file")))
            with cols[i % len(cols)], st.container(border=True):
                st.caption(f"Chart {i + 1} · {chart.get('title', '')}")
                if png:
                    st.image(png, use_container_width=True)
                else:
                    st.caption("Image not available.")

    rows = [
        [
            escape(str(f["label"])),
            f"<b>{escape(_fmt(f['value'], ''))}</b>",
            escape(str(f.get("unit", ""))),
        ]
        for f in facts
    ]
    left, right = st.columns([2, 1])
    with left, st.container(key="pane-narrative"):
        st.markdown(h.pane_header("Answer facts", "from results.json"), unsafe_allow_html=True)
        st.markdown(h.table(["Fact", "Value", "Unit"], rows, right=(1,)), unsafe_allow_html=True)
    with right, st.container(key="pane-verify"):
        st.markdown(
            h.pane_header("How it was verified", "from the event log"), unsafe_allow_html=True
        )
        for kind, text in _trail(view):
            icon = {"ok": "✓", "bad": "✕", "warn": "!"}[kind]
            st.markdown(
                f'<div class="flag"><span class="ic {kind}">{icon}</span><span>{text}</span></div>',
                unsafe_allow_html=True,
            )
        st.markdown(h.pane_header("Exports"), unsafe_allow_html=True)
        _exports(view, facts, charts)
        _reproduce(live, view)

    _decision(live, view, canvas.phase == "approved")
    _follow_up(live, view)


def _exports(view: RunView, facts: list[dict[str, Any]], charts: list[dict[str, Any]]) -> None:
    rec = view.record
    if view.code:
        st.download_button(
            "↓ analysis.py", analysis_script(view), f"analysis_{rec.run_id}.py", "text/x-python",
            key=f"dl-code-{rec.run_id}",
        )  # fmt: skip
    pngs = [(c, view.artifacts.get(str(c.get("file")))) for c in charts]
    for i, (c, png) in enumerate(pngs):
        if png:
            st.download_button(
                f"↓ {str(c.get('title', c.get('file')))[:36]} (PNG)", png, str(c["file"]), "image/png",
                key=f"dl-png-{rec.run_id}-{i}",
            )  # fmt: skip
    images = [ChartImage(str(c.get("title", "")), png) for c, png in pngs if png]
    pdf = _pdf(
        rec.run_id + _human_label(view),
        {
            "question": rec.question,
            "facts": facts,
            "charts": images,
            "reviewer_status": f"Approved (message {rec.messages}/12)",
            "human_status": _human_label(view),
            "run_id": rec.run_id,
            "dataset_name": str(st.session_state.get("source", {}).get("name", "dataset")),
            "messages": rec.messages,
        },
    )
    st.download_button(
        "↓ report.pdf (1 page)", pdf, f"report_{rec.run_id}.pdf", "application/pdf",
        key=f"dl-pdf-{rec.run_id}",
    )  # fmt: skip


def _reproduce(live: LiveSession, view: RunView) -> None:
    rid = view.record.run_id
    key = f"repro-{rid}"
    if st.button(
        "Verify reproducibility", key=f"btn-{key}", disabled=live.running or not view.code
    ):
        with st.spinner("Re-running analysis.py in a fresh sandbox container…"):
            st.session_state[key] = live.verify(rid, analysis_script(view))
    result = st.session_state.get(key)
    if result is not None:
        kind = "ok" if result.reproducible else "bad"
        st.markdown(h.chip(escape(result.reason), kind), unsafe_allow_html=True)
    st.caption("Runs the exported script again and compares the answer facts.")


def _decision(live: LiveSession, view: RunView, approvable: bool) -> None:
    rec = view.record
    st.markdown(
        '<div class="approval"><b>Your decision</b><span class="muted">Reviewer approval does not '
        "finalize the report.</span></div>",
        unsafe_allow_html=True,
    )
    decided = rec.human_status != "none"
    b1, b2, _ = st.columns([1, 1.7, 9])
    reject = b1.button("Reject", key=f"reject-{rec.run_id}", disabled=decided)
    accept = b2.button(
        "Approve report",
        key=f"approve-{rec.run_id}",
        type="primary",
        disabled=decided or not approvable,
    )
    if accept or reject:
        problem = live.decide(rec.run_id, approve=accept)
        if problem:
            st.error(problem)
        else:
            st.rerun()
    if decided:
        st.caption(f"Human decision recorded: {rec.human_status}.")


def _follow_up(live: LiveSession, view: RunView, label: str = "Ask follow-up") -> None:
    rec = view.record
    f1, f2 = st.columns([6, 1.3])
    text = f1.text_input(
        "Follow-up",
        key=f"followup-{rec.run_id}",
        placeholder="Ask a follow-up in this session, e.g. “Which products in that region fell most?”",
        label_visibility="collapsed",
    )
    if f2.button(label, key=f"ask-follow-{rec.run_id}", type="primary", disabled=live.running):
        if text.strip():
            src = st.session_state["source"]
            live.ask(
                text.strip(), path=Path(src["path"]), sheet=st.session_state.get("sheet"),
                mode="selector", parent_run_id=rec.run_id if rec.reviewer_approved else None,
            )  # fmt: skip
            st.session_state["ws"] = "livewire"
            st.rerun()
    st.caption("A follow-up starts a new run with a fresh 12-message budget on the same dataset.")

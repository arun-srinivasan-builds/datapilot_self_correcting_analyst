"""Insights Studio: answer-first report. Until M3 only a labelled design preview can fill it.

Numbers in the preview are real pandas results from fixtures/sales_sample.csv (not agent output).
Exports are disabled: no artifact exists until a verified run (M5).
"""

from __future__ import annotations

from html import escape

import streamlit as st

from datapilot.ui import markup as h
from datapilot.ui.charts import columns, hbar, money_m, variants
from datapilot.ui.chrome import common_chips
from datapilot.ui.live import get_live
from datapilot.ui.preview import PreviewAnalysis, events_for, fixture_analysis
from datapilot.ui.viewmodel import build_canvas
from datapilot.ui.workspaces.insights_live import render_live


@st.cache_data(show_spinner=False)
def _analysis() -> PreviewAnalysis | None:
    return fixture_analysis()


def _decide(choice: str) -> None:
    st.session_state["human"] = choice


def _open_preview() -> None:
    st.session_state["preview_key"] = "approved"
    st.session_state["human"] = None


def _follow_up() -> None:
    text = (st.session_state.get("followup") or "").strip()
    if text:
        st.session_state["human"] = "follow_up"
        st.session_state["followup_note"] = text


def render() -> None:
    live = get_live()
    view = live.latest_view()
    if live.running:
        st.markdown(
            h.toolbar("Insights Studio", common_chips(st.session_state.get("loaded"))),
            unsafe_allow_html=True,
        )
        st.info(
            "A run is in progress — watch it in Agent Livewire. Results appear here when it ends."
        )
        return
    if view is not None:
        render_live(live, view)
        return
    loaded = st.session_state.get("loaded")
    key = st.session_state.get("preview_key")
    events = events_for(key, st.session_state.get("human"))
    canvas = build_canvas(events)
    s = canvas.state
    has_result = s.phase in ("approved", "limit_reached")
    a = _analysis() if has_result else None

    chips = common_chips(loaded)
    if has_result:
        chips.append(
            h.chip(f"Reviewer: Approved · {s.message_count}/12", "ok")
            if s.phase == "approved"
            else h.chip("Reviewer: Unapproved · 12/12", "bad")
        )
        human = {
            "none": "Pending",
            "approved": "Approved",
            "rejected": "Rejected",
            "follow_up": "Follow-up",
        }[s.human]
        chips.append(h.chip(f"Human: {human}", "ok" if s.human == "approved" else "info"))
    st.markdown(h.toolbar("Insights Studio", chips), unsafe_allow_html=True)

    if not has_result or a is None:
        st.markdown(
            '<div class="dp-empty"><h3>No analysis yet</h3>Insights Studio shows the verified answer, key figures, '
            "charts and exports of a finished run. Run a question in Ask & Explore, or open a clearly "
            "labelled design preview.</div>",
            unsafe_allow_html=True,
        )
        st.button("Open design preview", key="open-preview", on_click=_open_preview)
        return

    st.markdown(
        h.banner(
            "Numbers below are computed with pandas from fixtures/sales_sample.csv; the verification "
            "trail is a scripted preview. This is not output of a live agent run."
        ),
        unsafe_allow_html=True,
    )
    cat_name, reg_name = escape(a.top_category), escape(a.top_region)
    drop = a.category_change[0][1]
    reg_drop = a.region_change[0][1]
    pct = (a.sep_total / a.aug_total - 1) * 100
    status_chip = (
        h.chip(f"Reviewer approved · msg {s.message_count}/12", "ok")
        if s.phase == "approved"
        else h.chip("UNAPPROVED — limit 12/12, partial result", "bad")
    )
    human_chip = {
        "none": h.chip("Human approval pending", "info"),
        "approved": h.chip("Human approved", "ok"),
        "rejected": h.chip("Human rejected", "bad"),
        "follow_up": h.chip("Follow-up requested", "info"),
    }[s.human]
    st.markdown(
        '<div class="report"><div class="q"><b>Question</b> · Which category had the biggest revenue drop in '
        "September vs August, and which region caused most of it?</div>"
        f'<p class="answer">{cat_name} fell the most, down <span class="neg">{money_m(drop)[:]}</span> from August '
        f"to September, driven by <em>{reg_name}</em> ({money_m(reg_drop)}), partly offset by growth in the other "
        f"regions.</p>{status_chip} {human_chip} {h.chip(f'{a.rows:,} rows analysed')}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        h.strip(
            [
                (
                    "Sep revenue",
                    money_m(a.sep_total),
                    f'<span class="neg">{pct:+.1f}% vs Aug</span>',
                ),
                ("Aug revenue", money_m(a.aug_total), "baseline"),
                (
                    "Largest category drop",
                    f'<span class="neg">{money_m(drop, True)}</span>',
                    cat_name,
                ),
                (
                    "Main regional cause",
                    f'<span class="neg">{money_m(reg_drop, True)}</span>',
                    f"{reg_name} · within {cat_name}",
                ),
                (
                    "Offset elsewhere",
                    f'<span class="pos">{money_m(a.offset, True)}</span>',
                    "other regions",
                ),
            ]
        ),
        unsafe_allow_html=True,
    )

    l1 = (
        '<div class="legend"><span><i class="l-err"></i>Largest decrease</span><span><i class="l-dim"></i>Other '
        'decreases</span><span><i class="l-active"></i>Increase</span></div>'
    )
    l2 = '<div class="legend"><span><i class="l-err"></i>Decrease</span><span><i class="l-active"></i>Increase</span></div>'
    l3 = (
        '<div class="legend"><span><i class="l-err"></i>September (selected month)</span><span><i class="l-dim">'
        "</i>Other months</span></div>"
    )
    c1 = variants(
        hbar,
        list(a.category_change),
        "Revenue change by category",
        "Revenue change (₹ million)",
        a.top_category,
        wide=1000,
        mid=700,
    )
    c2 = variants(
        hbar,
        list(a.region_change),
        f"{a.top_category}: change by region",
        "Revenue change (₹ million)",
        a.top_region,
        wide=700,
        mid=480,
    )
    c3 = variants(
        columns,
        list(a.monthly),
        "Revenue by month",
        "Revenue (₹ million)",
        "2026-09",
        wide=700,
        mid=480,
    )
    peak = max(abs(v) for _, v in a.category_change) or 1.0
    trows = []
    for name, v in sorted(a.category_change, key=lambda kv: kv[1]):
        aug, sep = a.category_aug[name], a.category_sep[name]
        cls = "neg" if v < 0 else "pos"
        bar = f'<div class="dbar"><i class="{"n" if v < 0 else "p"}" style="width:{abs(v) / peak * 50:.0f}%"></i></div>'
        trows.append(
            [
                f"<b>{escape(name)}</b>",
                money_m(aug),
                money_m(sep),
                f'<b class="{cls}">{money_m(v, True)}</b>',
                f'<span class="{cls}">{(sep / aug - 1) * 100:+.1f}%</span>',
                bar,
            ]
        )
    trows.append(
        [
            "<b>All categories</b>",
            f"<b>{money_m(a.aug_total)}</b>",
            f"<b>{money_m(a.sep_total)}</b>",
            f'<b class="neg">{money_m(a.sep_total - a.aug_total, True)}</b>',
            f'<b class="neg">{pct:+.1f}%</b>',
            "",
        ]
    )
    detail = h.table(
        ["Category", "August", "September", "Change", "%", "Contribution"],
        trows,
        right=(1, 2, 3, 4),
    )

    st.markdown(
        '<div class="dp-grid"><div class="vgrid">'
        f'<section class="pane chart c7" aria-label="Category change"><header>Chart 1 · Change by category<span class="sp"></span><span>Sep vs Aug</span></header>{l1}<div class="body">{c1}</div></section>'
        f'<section class="pane chart c5" aria-label="Region contribution"><header>Chart 2 · {cat_name} by region<span class="sp"></span><span>drill-down</span></header>{l2}<div class="body">{c2}</div></section>'
        f'<section class="pane c7" aria-label="Detail table"><header>Category detail<span class="sp"></span><span>Aug → Sep</span></header>{detail}</section>'
        f'<section class="pane chart c5" aria-label="Monthly revenue"><header>Chart 3 · Monthly revenue<span class="sp"></span><span>Jun–Sep</span></header>{l3}<div class="body">{c3}</div></section>'
        "</div></div>",
        unsafe_allow_html=True,
    )

    narr, ver = st.columns([2, 1])
    with narr, st.container(key="pane-narrative"):
        st.markdown(
            h.pane_header("Analyst narrative", "scripted preview · not AI output"),
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="narr two"><div>'
            f"<p>Total revenue fell {abs(pct):.1f}% from August to September. {cat_name} accounts for the largest "
            f"category decline at {money_m(drop)}.</p>"
            f"<p>Inside {cat_name}, <b>{reg_name}</b> fell {money_m(reg_drop)}, while the other regions together grew "
            f'{money_m(a.offset)}.</p><p class="src">Method: revenue = units × unit_price × (1 − discount). '
            "Figures computed with pandas from the sample fixture.</p></div><div>"
            '<div style="font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);'
            'font-weight:600;margin-bottom:6px">How it was verified · from the event log</div>'
            '<div class="flag"><span class="ic bad">✕</span><span>Execution 1 failed: <span class="mono">'
            "KeyError: revenue</span> → Coder repaired from the error</span></div>"
            '<div class="flag"><span class="ic warn">!</span><span>Reviewer asked for axis units and an offset note '
            "→ Coder revised</span></div>"
            '<div class="flag"><span class="ic ok">✓</span><span>Execution 3 exit 0 · Reviewer APPROVED '
            f"(msg {s.message_count}/12)</span></div></div></div>",
            unsafe_allow_html=True,
        )
    with ver, st.container(key="pane-verify"):
        st.markdown(h.pane_header("Verification & exports"), unsafe_allow_html=True)
        reviewer = (
            '<span class="chip ok"><i class="dot"></i>Approved · msg 9</span>'
            if s.phase == "approved"
            else '<span class="chip bad"><i class="dot"></i>Unapproved</span>'
        )
        st.markdown(
            '<div class="verify"><div class="row"><span class="muted">Reviewer</span>'
            + reviewer
            + "</div>"
            '<div class="row"><span class="muted">Human</span>' + human_chip + "</div></div>",
            unsafe_allow_html=True,
        )
        for i, label in enumerate(("analysis.py", "PNG · 2 charts", "PDF · 1 page")):
            st.button(
                f"↓ {label}",
                key=f"dl-{i}",
                disabled=True,
                help="Exports are generated from a verified live run (M5).",
            )
        st.caption("Exports unlock after a verified live run — none exists in the design preview.")

    with st.container(key="pane-decision"):
        st.markdown(
            '<div class="approval"><b>Your decision</b><span class="muted">Reviewer approval does not finalize '
            "the report.</span></div>",
            unsafe_allow_html=True,
        )
        b1, b2, _sp = st.columns([1, 1.7, 9])
        b1.button("Reject", key="reject", on_click=_decide, args=("rejected",))
        b2.button(
            "Approve report",
            key="approve",
            type="primary",
            on_click=_decide,
            args=("approved",),
            disabled=s.phase != "approved",
            help="Disabled: only a Reviewer-approved run can be approved by a human.",
        )
        f1, f2 = st.columns([6, 1.3])
        f1.text_input(
            "Follow-up",
            key="followup",
            placeholder="Ask a follow-up in this session, e.g. “Which South products fell most?”",
            label_visibility="collapsed",
        )
        f2.button("Ask follow-up", key="ask-follow", type="primary", on_click=_follow_up)
        note = st.session_state.get("followup_note")
        if s.human == "follow_up" and note:
            st.info(
                f"Follow-up recorded: “{note}”. It will start a new run with a fresh 12-message "
                "budget once live agents exist (M3)."
            )
        else:
            st.caption(
                "A follow-up starts a new run with a fresh 12-message budget and keeps this dataset "
                "and history."
            )

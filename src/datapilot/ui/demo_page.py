"""The public demo page: one guided, plain-language story over RECORDED real runs.

Visitors see: what DataPilot is -> the question -> the AI team working (animated replay of the real
events) -> the answer with premium charts -> why it can be trusted and what to check. It never calls
a model or the sandbox. The private admin site (live runs) uses the separate workspaces.
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

import streamlit as st

from datapilot.events import EventType
from datapilot.ingestion import load_dataset
from datapilot.reports.pdf import ChartImage, build_pdf
from datapilot.ui import demo
from datapilot.ui.demo_charts import build_figure, compact, has_data, takeaway
from datapilot.ui.demo_flow import HEIGHT, workflow_html
from datapilot.ui.demo_frames import build_frames, trust_checks
from datapilot.ui.live import RunView

CSS = Path(__file__).resolve().parent / "static" / "demo.css"
FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "sales_sample.csv"
RUN_TEXT = {
    "normal-run": (
        "Run A · A smooth run",
        "The team gets it right first time. Best for seeing the whole flow clearly.",
    ),
    "fault-injection": (
        "Run B · Watch a mistake get fixed",
        "We planted an error on purpose. Watch the team catch it and repair it by itself.",
    ),
}


def _css() -> str:
    return CSS.read_text(encoding="utf-8")


@st.cache_resource(show_spinner=False)
def _dataset_facts() -> dict[str, Any]:
    if not FIXTURE.is_file():
        return {}
    frame = load_dataset(FIXTURE).frame
    dates = frame["order_date"].astype(str)
    return {
        "rows": len(frame),
        "start": dates.min(),
        "end": dates.max(),
        "cols": list(frame.columns),
    }


def _results(view: RunView) -> dict[str, Any]:
    raw = view.artifacts.get("results.json")
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _fmt_value(value: Any) -> tuple[str, bool]:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return str(value), False
    return compact(float(value)), float(value) < 0


def _hero() -> str:
    team = (
        ("#4f5bd5", "Planner"),
        ("#2fb5c2", "Coder"),
        ("#e0a31a", "Executor"),
        ("#3fc58d", "Reviewer"),
    )
    chips = "".join(
        f'<span class="dp-chip"><b style="background:{c}"></b>{n}</span>' for c, n in team
    )
    return (
        '<div class="dp-top"><div class="dp-logo">D</div><div class="dp-brand">DataPilot</div>'
        '<div class="dp-pill"><i></i>Recorded real run · demo</div></div>'
        '<div class="dp-hero"><h1>Ask a business question.<br>Watch an AI team answer it — and check its own work.</h1>'
        "<p>DataPilot is a team of four AI agents. They write real code, run it on your data, "
        "fix their own mistakes, and only give you an answer once an independent reviewer approves it. "
        "Everything below is a <b>real recording</b> of that team at work.</p>"
        f'<div class="dp-team">{chips}</div></div>'
        '<div class="dp-how">'
        '<a href="#question"><span class="n">1</span><b>The question</b><span>What we asked</span></a>'
        '<a href="#watch"><span class="n">2</span><b>Watch the team</b><span>Live replay</span></a>'
        '<a href="#answer"><span class="n">3</span><b>The answer</b><span>Numbers and charts</span></a>'
        '<a href="#trust"><span class="n">4</span><b>Why trust it</b><span>What to check</span></a></div>'
    )


def _section(anchor: str, num: int, tag: str, title: str, lead: str) -> str:
    return (
        f'<div class="dp-sec" id="{anchor}"><div class="tag"><i>{num}</i>{escape(tag)}</div>'
        f"<h2>{escape(title)}</h2><p>{escape(lead)}</p></div>"
    )


def _question(view: RunView) -> None:
    facts = _dataset_facts()
    meta = ""
    if facts:
        meta = (
            f"<span>{facts['rows']:,} sales orders</span>"
            f"<span>{escape(facts['start'])} to {escape(facts['end'])}</span>"
            "<span>region · category · product · units · price · discount</span>"
        )
    st.markdown(
        _section(
            "question",
            1,
            "The question",
            "What did we ask?",
            "A plain-English business question, asked about a sales spreadsheet. No code, no formulas.",
        )
        + f'<div class="dp-card"><div class="dp-q">“{escape(view.record.question)}”</div>'
        f'<div class="dp-meta">{meta}</div></div>',
        unsafe_allow_html=True,
    )


def _watch(view: RunView) -> None:
    frames = build_frames(view.events)
    rec = view.record
    st.markdown(
        _section(
            "watch",
            2,
            "Watch the team work",
            "Four AI agents, one job",
            "Press play (it starts by itself). Each step below is a real event from the recording, "
            "with the real time it took. Click any step to jump to it.",
        ),
        unsafe_allow_html=True,
    )
    # trusted template; every recorded value is JSON-escaped and only ever set via textContent
    st.iframe(workflow_html(frames, {"messages": rec.messages}), height=HEIGHT)


def _answer(view: RunView) -> None:
    data = _results(view)
    facts = [f for f in data.get("answer_facts", []) if isinstance(f, dict)]
    charts = [c for c in data.get("charts", []) if isinstance(c, dict)]
    text_facts = [f for f in facts if isinstance(f.get("value"), str)][:2] or facts[:2]
    big = " · ".join(escape(str(f["value"])) for f in text_facts)
    verdict = next((e for e in view.events if e.type is EventType.REVIEWER_APPROVED), None)
    verdict_text = ""
    if verdict is not None:
        lines = str(verdict.payload.get("text", "")).rstrip().splitlines()
        verdict_text = " ".join(ln for ln in lines if ln.strip() != "APPROVED").replace("**", "")
    st.markdown(
        _section(
            "answer",
            3,
            "The answer",
            "Here is what the team found",
            "The headline, the key numbers, and charts drawn from the program's own output.",
        )
        + '<div class="dp-answer"><div class="lbl">The answer</div>'
        f'<div class="big">{big}</div>'
        f'<div class="sub">{escape(verdict_text[:420])}</div></div>',
        unsafe_allow_html=True,
    )
    numeric = [
        f
        for f in facts
        if isinstance(f.get("value"), int | float) and not isinstance(f.get("value"), bool)
    ]
    if numeric:
        cards = ""
        for f in numeric[:6]:
            val, neg = _fmt_value(f["value"])
            cards += (
                f'<div class="dp-kpi"><div class="l">{escape(str(f["label"])[:90])}</div>'
                f'<div class="v{" neg" if neg else ""}">{escape(val)}</div>'
                f'<div class="u">{escape(str(f.get("unit", ""))[:40])}</div></div>'
            )
        st.markdown(f'<div class="dp-kpis">{cards}</div>', unsafe_allow_html=True)
    for i, chart in enumerate(charts):
        head = f"<h4>{escape(str(chart.get('title', 'Chart')))}</h4>"
        with st.container(key=f"chartcard-{view.record.run_id}-{i}"):
            if has_data(chart):
                why = takeaway(chart)
                st.markdown(
                    head
                    + (f'<div class="why">{escape(why)}</div>' if why else "")
                    + f'<div class="unit">Hover a bar for the exact value · units: {escape(str(chart.get("unit", "")))}</div>',
                    unsafe_allow_html=True,
                )
                st.plotly_chart(
                    build_figure(chart),
                    width="stretch",
                    config={"displayModeBar": False},
                    key=f"chart-{view.record.run_id}-{i}",
                )
            else:
                st.markdown(head, unsafe_allow_html=True)
                png = view.artifacts.get(str(chart.get("file")))
                if png:
                    st.image(png, width="stretch")


def _trust(view: RunView) -> None:
    items = ""
    for c in trust_checks(view.events):
        icon = "✓" if c.ok else "i"
        items += (
            f'<div class="dp-check"><div class="ic{"" if c.ok else " info"}">{icon}</div>'
            f"<div><b>{escape(c.title)}</b><span>{escape(c.body)}</span></div></div>"
        )
    st.markdown(
        _section(
            "trust",
            4,
            "Why you can trust it",
            "What to check — and how",
            "AI can make mistakes, so DataPilot is built to catch them. Here is the evidence from this recording.",
        )
        + f'<div class="dp-checks">{items}</div>'
        '<div class="dp-todo">'
        "<div><b>1 · Compare</b><span>Does the headline answer match the tallest bar or the biggest number in the charts?</span></div>"
        "<div><b>2 · Inspect</b><span>Open “Show the Python the agents wrote” below. It is plain, readable code you can review.</span></div>"
        "<div><b>3 · Switch runs</b><span>Choose Run B at the top to watch the team catch a crash and repair it themselves.</span></div>"
        "</div>",
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False, max_entries=4)
def _pdf(run_id: str, payload: dict[str, Any]) -> bytes:
    del run_id
    return build_pdf(**payload)


def _inspect(view: RunView) -> None:
    rec = view.record
    data = _results(view)
    st.markdown(
        '<div class="dp-sec"><h2 style="font-size:24px">Take it with you</h2>'
        "<p>Everything is downloadable, so you can check it yourself.</p></div>",
        unsafe_allow_html=True,
    )
    with st.expander("Show the Python the agents wrote"):
        st.code(view.code or "# not available", language="python")
    cols = st.columns(3)
    if view.code:
        header = f'"""DataPilot export - the exact script that ran and was approved (run {rec.run_id})."""\n'
        cols[0].download_button(
            "↓ analysis.py",
            header + view.code,
            f"analysis_{rec.run_id}.py",
            "text/x-python",
            key=f"dl-code-{rec.run_id}",
            width="stretch",
        )
    charts = [c for c in data.get("charts", []) if isinstance(c, dict)]
    images = [
        ChartImage(str(c.get("title", "")), view.artifacts[str(c.get("file"))])
        for c in charts
        if str(c.get("file")) in view.artifacts
    ]
    pdf = _pdf(
        rec.run_id,
        {
            "question": rec.question,
            "facts": data.get("answer_facts", []),
            "charts": images,
            "reviewer_status": f"Approved (message {rec.messages}/12)",
            "human_status": "Not applicable (recorded demo)",
            "run_id": rec.run_id,
            "dataset_name": "sales_sample.csv",
            "messages": rec.messages,
        },
    )
    cols[1].download_button(
        "↓ One-page PDF report",
        pdf,
        f"report_{rec.run_id}.pdf",
        "application/pdf",
        key=f"dl-pdf-{rec.run_id}",
        width="stretch",
    )
    if images:
        cols[2].download_button(
            "↓ Chart image (PNG)",
            images[0].png,
            "chart.png",
            "image/png",
            key=f"dl-png-{rec.run_id}",
            width="stretch",
        )


def render() -> None:
    st.markdown(f"<style>{_css()}</style>", unsafe_allow_html=True)
    runs = demo.recorded_runs()
    if not runs:
        st.error("The recorded demo data is not available.")
        return
    st.markdown(_hero(), unsafe_allow_html=True)
    keys = [k for k in RUN_TEXT if k in runs]
    st.markdown('<div class="dp-pick">', unsafe_allow_html=True)
    key = (
        st.segmented_control(
            "Choose a recording",
            keys,
            format_func=lambda k: RUN_TEXT[k][0],
            key="demo_run",
            default=keys[0],
            label_visibility="collapsed",
        )
        or keys[0]
    )
    st.markdown(f"<p>{escape(RUN_TEXT[key][1])}</p></div>", unsafe_allow_html=True)
    view = runs[key]
    _question(view)
    _watch(view)
    _answer(view)
    _trust(view)
    _inspect(view)
    rec = view.record
    st.markdown(
        '<div class="dp-foot">Recorded real run · model gpt-6-luna · '
        f"{rec.input_tokens + rec.output_tokens:,} tokens · {rec.messages} of 12 allowed agent messages used.<br>"
        "This public page replays recordings; nothing on it calls an AI model or runs code.</div>",
        unsafe_allow_html=True,
    )

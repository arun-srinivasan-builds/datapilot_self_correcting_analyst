"""Builds the static design mockups (HTML + CSS) from fixture-derived numbers.

    .venv\\Scripts\\python docs/mockups/build.py      # writes *.html next to this file
    .venv\\Scripts\\python docs/mockups/capture.py    # writes png/*.png (needs Playwright + Edge)

Design only: this is NOT the Streamlit implementation. Numbers come from fixtures/sales_sample.csv
(computed with pandas); agent text is illustrative copy that shows what real events will carry.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CSV = ROOT / "fixtures" / "sales_sample.csv"

# --------------------------------------------------------------------------- data
df = pd.read_csv(CSV)
df["revenue"] = df["units"] * df["unit_price"] * (1 - df["discount"])
df["month"] = df["order_date"].str[:7]
cat = df.pivot_table(index="category", columns="month", values="revenue", aggfunc="sum")
cat_change = (cat["2026-09"] - cat["2026-08"]).sort_values()
top_cat = cat_change.index[0]
reg = df[(df.category == top_cat) & df.month.isin(["2026-08", "2026-09"])].pivot_table(
    index="region", columns="month", values="revenue", aggfunc="sum"
)
reg_change = (reg["2026-09"] - reg["2026-08"]).sort_values()
monthly = df.groupby("month")["revenue"].sum()


def m(v: float, sign: bool = False) -> str:
    s = f"{abs(v) / 1e6:,.2f}"
    if sign:
        return ("+" if v >= 0 else "−") + "₹" + s + "M"
    return "₹" + s + "M"


TOP_DROP = cat_change.iloc[0]
TOP_REG = reg_change.index[0]
TOP_REG_VAL = reg_change.iloc[0]
OFFSET = reg_change.iloc[1:].sum()
AUG, SEP = monthly["2026-08"], monthly["2026-09"]
SEP_PCT = (SEP / AUG - 1) * 100

# --------------------------------------------------------------------------- shell
ICON = {
    "ask": '<svg viewBox="0 0 24 24"><ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6"/><path d="M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/></svg>',
    "live": '<svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="19" cy="19" r="2"/><path d="M7 12h5l5-6M12 12l5 6"/></svg>',
    "ins": '<svg viewBox="0 0 24 24"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>',
}
NAV = [
    ("ask", "Ask & Explore", "ask-explore.html"),
    ("live", "Agent Livewire", "livewire-running.html"),
    ("ins", "Insights Studio", "insights-studio.html"),
]


def shell(active: str, crumb: str, toolbar: str, body: str, title: str) -> str:
    navs = ""
    for k, label, href in NAV:
        cur = ' is-active" aria-current="page' if k == active else ""
        short = label.split(" ")[-1]
        navs += f'<a class="nav{cur}" href="{href}" aria-label="{label}">{ICON[k]}<span>{short}</span></a>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><link rel="stylesheet" href="mockup.css"></head>
<body><div class="app">
<nav class="rail" aria-label="Workspaces"><div class="logo" aria-hidden="true">D</div>{navs}<div class="grow"></div></nav>
<div class="main">
<header class="toolbar"><div class="crumb">DataPilot <span>/ {escape(crumb)}</span></div><div class="sp"></div>{toolbar}</header>
{body}
</div></div></body></html>"""


def chip(text: str, kind: str = "", cls: str = "") -> str:
    return f'<span class="chip {kind} {cls}"><i class="dot"></i>{escape(text)}</span>'


COMMON_TB = (
    chip("sales_sample.csv · 12,480 rows", "info", "hide-m")
    + chip("gpt-6-luna", "live", "hide-m")
    + '<span class="mock-flag hide-m">DESIGN MOCKUP · representative data</span>'
)

# --------------------------------------------------------------------------- Ask & Explore
cols = [
    ("order_date", "datetime", 0, int(df.order_date.nunique())),
    ("region", "text", 0, 4),
    ("category", "text", 0, 5),
    ("product", "text", 0, int(df["product"].nunique())),
    ("units", "integer", 0, int(df.units.nunique())),
    ("unit_price", "integer", 0, int(df.unit_price.nunique())),
    ("discount", "float", 0, int(df.discount.nunique())),
]


def ask_explore() -> str:
    head = "".join(
        f'<th class="{"r" if t in ("integer", "float") else ""}">{n}<span class="ty">{t}</span></th>'
        for n, t, _, _ in cols
    )
    rows = "".join(
        "<tr>"
        + "".join(
            f'<td class="{"r" if cols[i][1] in ("integer", "float") else ""}">{escape(str(v))}</td>'
            for i, v in enumerate(r)
        )
        + "</tr>"
        for r in df.head(14)[[c[0] for c in cols]].itertuples(index=False)
    )
    prof = "".join(
        f'<tr><td>{n}</td><td>{t}</td><td class="r {"nullc" if nl else ""}">{nl}</td><td class="r">{u:,}</td>'
        f'<td><div class="bar"><i style="width:{min(100, 100 * u / 12480 * 8 + 6):.0f}%"></i></div></td></tr>'
        for n, t, nl, u in cols
    )
    body = f"""<div class="strip" aria-label="Dataset profile">
<div><div class="l">Rows</div><div class="v num">12,480</div><div class="d muted">1 sheet · CSV</div></div>
<div><div class="l">Columns</div><div class="v num">7</div><div class="d muted">4 text · 3 numeric</div></div>
<div><div class="l">Missing values</div><div class="v num">0</div><div class="d pos">✓ none detected</div></div>
<div><div class="l">Date column</div><div class="v" style="font-size:18px">order_date</div><div class="d muted">2026-06-01 → 2026-09-30</div></div>
<div><div class="l">Duplicates</div><div class="v num">0</div><div class="d pos">✓ clean</div></div>
</div>
<main class="canvas ae">
<section class="pane" aria-label="Data source"><header>Data source</header><div class="body">
<div class="drop"><b>Drop CSV or XLSX</b>or browse · up to 25 MB</div>
<ul class="list" style="margin-top:10px">
<li class="sel"><span class="ic ok">●</span><span>sales_sample.csv</span><span class="sp"></span><span class="muted num">12,480</span></li>
<li><span class="ic info">○</span><span>sales_alt_schema.csv</span><span class="sp"></span><span class="muted num">3,210</span></li>
<li><span class="ic info">○</span><span>multisheet.xlsx</span><span class="sp"></span><span class="muted">3 sheets</span></li>
</ul>
<div class="field" style="margin-top:14px"><label>Sheet</label><div class="select"><span>Orders</span><span class="muted">▾</span></div></div>
<div class="eyebrow" style="margin:14px 0 6px">Quality</div>
<div class="flag"><span class="ic ok">✓</span><span><b>Schema readable</b> · 7 columns typed</span></div>
<div class="flag"><span class="ic ok">✓</span><span><b>No missing values</b></span></div>
<div class="flag"><span class="ic info">i</span><span><b>Date column</b> detected: order_date</span></div>
</div></section>

<section class="pane" aria-label="Data preview"><header>Preview · first 14 of 12,480 rows<span class="sp"></span><span class="hide-m">Column profile ↓</span></header>
<div class="tscroll"><table class="t"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>
<header style="border-top:1px solid var(--line)">Column profile</header>
<div class="tscroll"><table class="t"><thead><tr><th>Column</th><th>Type</th><th class="r">Nulls</th><th class="r">Unique</th><th>Distinct values</th></tr></thead>
<tbody>{prof}</tbody></table></div></section>

<aside class="pane" aria-label="Ask a question"><header>Question<span class="sp"></span><span class="seg"><span class="on">Guarded</span><span>Round-robin</span></span></header>
<div class="body">
<div class="field"><label for="q">Your question</label>
<textarea id="q" class="q" readonly>Which category had the biggest revenue drop in September vs August, and which region caused most of it?</textarea></div>
<div style="display:flex;gap:8px;align-items:center"><span class="btn primary">Run analysis</span><span class="muted" style="font-size:12px">Max 12 agent messages</span></div>
<div class="eyebrow" style="margin:16px 0 6px">Suggested from this dataset</div>
<div class="sugg" style="margin-top:0">
<div>Revenue by month and category</div>
<div>Top 5 products by revenue in September</div>
<div>Does a higher discount raise units sold?</div>
</div>
<div class="eyebrow" style="margin:16px 0 6px">Session history</div>
<div class="hist"><div><span class="ic ok">✓</span><span>Biggest drop Sep vs Aug · <span class="muted">Reviewer approved · 9/12</span></span></div>
<div><span class="ic warn">!</span><span>Revenue by region · <span class="muted">Unapproved · 12/12</span></span></div></div>
</div></aside>
</main>"""
    tb = COMMON_TB + chip("Pricing not configured", "warn", "hide-m") + chip("Idle", "", "")
    return shell("ask", "Ask & Explore", tb, body, "DataPilot — Ask & Explore (mockup)")


# --------------------------------------------------------------------------- Livewire
FIRST_CODE = """<span class="k">import</span> pandas <span class="k">as</span> pd, json
<span class="k">import</span> matplotlib; matplotlib.use(<span class="s">"Agg"</span>)
df = pd.read_csv(DATA_PATH, parse_dates=[<span class="s">"order_date"</span>])
df[<span class="s">"month"</span>] = df[<span class="s">"order_date"</span>].dt.to_period(<span class="s">"M"</span>)
<span class="hl">rev = df.groupby([<span class="s">"month"</span>, <span class="s">"category"</span>])[<span class="s">"revenue"</span>].sum().unstack()</span>
change = (rev.loc[<span class="s">"2026-09"</span>] - rev.loc[<span class="s">"2026-08"</span>]).sort_values()"""
KEYERR = """Traceback (most recent call last):
  File "analysis.py", line 5, in &lt;module&gt;
    rev = df.groupby(["month", "category"])["revenue"].sum().unstack()
KeyError: 'Column not found: revenue'
exit_code=1"""
FIXED_CODE = """<span class="c"># Coder revision 2 — derived the missing revenue column</span>
<span class="k">import</span> pandas <span class="k">as</span> pd, json
<span class="k">import</span> matplotlib; matplotlib.use(<span class="s">"Agg"</span>)
df = pd.read_csv(DATA_PATH, parse_dates=[<span class="s">"order_date"</span>])
<span class="add">df[<span class="s">"revenue"</span>] = df.units * df.unit_price * (<span class="k">1</span> - df.discount)</span>
df[<span class="s">"month"</span>] = df[<span class="s">"order_date"</span>].dt.to_period(<span class="s">"M"</span>)
rev = df.groupby([<span class="s">"month"</span>, <span class="s">"category"</span>])[<span class="s">"revenue"</span>].sum().unstack()"""
FAULT_ERR = """Traceback (most recent call last):
  File "analysis.py", line 4, in &lt;module&gt;
    df["revenue"] = df.units * df.unit_price * (1 - df.discount)
AttributeError: 'DataFrame' object has no attribute 'units'
exit_code=1"""
FAULT_CODE = """<span class="c"># Coder output AFTER test-harness mutation (column 'units' renamed to 'qty')</span>
df = pd.read_csv(DATA_PATH, parse_dates=[<span class="s">"order_date"</span>])
<span class="del">df[<span class="s">"revenue"</span>] = df.<span class="k">qty</span> * df.unit_price * (<span class="k">1</span> - df.discount)</span>"""
REVIEW_FB = """1. Chart 2 has no y-axis label or unit — add "Revenue change (₹ million)".
2. State that South's decline (−5.60M) is partly offset by growth in the other regions.
Executor output matches results.json; numbers verified."""
APPROVE_TXT = """Verified: figures in stdout match results.json; both charts have title, axis labels and units;
answer addresses category and region.
APPROVED"""

NODE_ORDER = ["Planner", "Coder", "Executor", "Reviewer", "Human"]
NODE_SUB = {
    "Planner": "plans",
    "Coder": "writes / repairs code",
    "Executor": "runs in sandbox",
    "Reviewer": "checks · only approver",
    "Human": "approval stage",
}
H = {"Planner": 20, "Coder": 250, "Executor": 480, "Reviewer": 710, "Human": 960}


def flow_svg(st: dict, edges: dict, fault: bool) -> str:
    """Horizontal + vertical lane SVGs (CSS swaps them at <768px)."""

    def node(name: str, x: int, y: int, w: int, h: int) -> str:
        status, label = st[name]
        extra = ""
        if name == "Coder" and fault:
            extra = (
                f'<g class="badge-fault"><rect x="{x}" y="{y - 22}" width="{w}" height="18" rx="2"/>'
                f'<text x="{x + w / 2}" y="{y - 9}" text-anchor="middle">TEST FAULT INJECTED</text></g>'
            )
        return (
            f'<g class="node is-{status}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3"/>'
            f'<text x="{x + 12}" y="{y + 26}">{name}</text><text class="sub" x="{x + 12}" y="{y + 44}">{NODE_SUB[name]}</text>'
            f'<text class="st" x="{x + 12}" y="{y + h - 10}">{escape(label)}</text>{extra}</g>'
        )

    labels: list[str] = []

    def e(
        name: str,
        d: str,
        label: str = "",
        lx: int = 0,
        ly: int = 0,
        kind: str = "",
        rot: bool = False,
    ) -> str:
        cls = edges.get(name, "")
        if label and cls:
            tf = f' transform="rotate(-90 {lx} {ly})"' if rot else ""
            labels.append(
                f'<text class="elabel {kind}" x="{lx}" y="{ly}" text-anchor="middle"{tf}>{label}</text>'
            )
        return f'<path class="edge {cls}" d="{d}" marker-end="url(#a)"/>'

    defs = (
        '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0 0L10 5L0 10z" fill="#9aa7bd"/></marker></defs>'
    )
    hz = [defs]
    for n in NODE_ORDER:
        hz.append(node(n, H[n], 44, 170, 76))
    hz += [
        e("p_c", "M190 82H248"),
        e("c_e", "M420 82H478"),
        e("e_r", "M650 82H708"),
        e("r_h", "M880 82H958"),
        e(
            "repair",
            "M565 120C565 168 372 168 372 122",
            "REPAIR · error returned to Coder",
            468,
            176,
            "repair",
        ),
        e(
            "feedback",
            "M795 120C795 258 300 258 300 122",
            "FEEDBACK · Reviewer to Coder",
            548,
            238,
            "feedback",
        ),
    ]
    hz += labels
    labels.clear()
    horiz = f'<svg class="h" viewBox="0 0 1150 262" role="img" aria-label="Agent workflow lanes">{"".join(hz)}</svg>'
    vz = [defs]
    ys = {"Planner": 14, "Coder": 120, "Executor": 226, "Reviewer": 332, "Human": 438}
    for n in NODE_ORDER:
        vz.append(node(n, 20, ys[n] + (22 if n == "Coder" and fault else 0), 230, 76))
    off = 22 if fault else 0
    vz += [
        e("p_c", f"M135 90V{118 + off}"),
        e("c_e", f"M135 {196 + off}V{224 + off}"),
        e("e_r", f"M135 {302 + off}V{330 + off}"),
        e("r_h", f"M135 {408 + off}V{436 + off}"),
        e(
            "repair",
            f"M250 {264 + off}C302 {264 + off} 302 {158 + off} 252 {158 + off}",
            "REPAIR",
            273,
            211 + off,
            "repair",
            rot=True,
        ),
        e(
            "feedback",
            f"M250 {370 + off}C372 {370 + off} 372 {170 + off} 252 {170 + off}",
            "FEEDBACK",
            322,
            270 + off,
            "feedback",
            rot=True,
        ),
    ]
    vz += labels
    vert = f'<svg class="v" viewBox="0 0 380 {540 + off}" role="img" aria-label="Agent workflow lanes">{"".join(vz)}</svg>'
    return f'<div class="lanes">{horiz}{vert}</div>'


def cells(spec: list[str]) -> str:
    spec = spec + [""] * (12 - len(spec))
    return (
        '<span class="cells" aria-hidden="true">'
        + "".join(f'<i class="{c}"></i>' for c in spec)
        + "</span>"
    )


def feed_html(items: list[tuple[str, str, str, str]]) -> str:
    out = []
    for n, who, text, cls in items:
        out.append(
            f'<div class="m {cls}"><span class="s">{n}</span><div><span class="who">{who}</span> '
            f'<span class="muted">{escape(text) if cls != "raw" else text}</span></div></div>'
        )
    return "".join(out)


S = lambda status, label: (status, label)  # noqa: E731
IDLE = {n: S("idle", "IDLE") for n in NODE_ORDER}
PLAN = "1) revenue = units × unit_price × (1 − discount)  2) group by month + category (Aug vs Sep)  3) biggest drop  4) split by region  5) 2 charts"

STATES: dict[str, dict] = {
    "idle": dict(
        label="Idle",
        count=0,
        cells=[],
        run_chip=("Idle · armed", ""),
        mode="Guarded selector",
        nodes=IDLE | {"Human": S("idle", "NOT STARTED")},
        edges={},
        feed=[],
        tab="Code",
        body='<div class="body muted">No run yet. The canvas stays empty until a real <span class="mono">run_started</span> event arrives — nothing is simulated.</div>',
        outcome=("", "No run", "Submit a question in Ask &amp; Explore to start."),
        facts=(0, 0, 0, "0 / 0"),
        fault=False,
    ),
    "running": dict(
        label="Running",
        count=1,
        cells=["on"],
        run_chip=("Running", "live"),
        mode="Guarded selector",
        nodes=IDLE
        | {
            "Planner": S("done", "DONE · 1 MSG"),
            "Coder": S("active", "WRITING CODE"),
            "Human": S("idle", "NOT STARTED"),
        },
        edges={"p_c": "used"},
        feed=[
            ("•", "app", "run_started · question + dataset fingerprint", "ev"),
            ("1", "Planner", PLAN, ""),
            ("•", "selector", "speaker_selected → Coder", "ev"),
        ],
        tab="Plan",
        body=f'<pre class="code" style="white-space:pre-wrap">{escape(PLAN)}</pre>',
        outcome=(
            "run",
            "Run in progress",
            "Coder is working. Counter 1/12 counts only real agent messages.",
        ),
        facts=(0, 0, 0, "1,842 / 311"),
        fault=False,
    ),
    "exec-error": dict(
        label="Execution error",
        count=3,
        cells=["on", "on", "err"],
        run_chip=("Execution error", "bad"),
        mode="Guarded selector",
        nodes=IDLE
        | {
            "Planner": S("done", "DONE"),
            "Coder": S("done", "DONE"),
            "Executor": S("error", "ERROR · EXIT 1"),
            "Human": S("idle", "NOT STARTED"),
        },
        edges={"p_c": "used", "c_e": "used"},
        feed=[
            ("1", "Planner", PLAN, ""),
            ("2", "Coder", "code_generated · analysis.py (23 lines)", ""),
            ("•", "Executor", "exec_started · code hash 9f3a…", "ev"),
            ("3", "Executor", "exec_result · error · KeyError: 'Column not found: revenue'", "err"),
        ],
        tab="Error",
        body=f'<pre class="code">{FIRST_CODE}</pre><pre class="err">{KEYERR}</pre>',
        outcome=(
            "bad",
            "Execution failed — real stderr captured",
            "Error text goes verbatim to the Coder next.",
        ),
        facts=(0, 0, 0, "2,306 / 904"),
        fault=False,
    ),
    "repair": dict(
        label="Repair",
        count=3,
        cells=["on", "on", "err"],
        run_chip=("Repairing · attempt 1", "warn"),
        mode="Guarded selector",
        nodes=IDLE
        | {
            "Planner": S("done", "DONE"),
            "Coder": S("active", "REPAIRING · ATTEMPT 1"),
            "Executor": S("error", "ERROR · EXIT 1"),
            "Human": S("idle", "NOT STARTED"),
        },
        edges={"p_c": "used", "c_e": "used", "repair": "repair"},
        feed=[
            ("3", "Executor", "exec_result · error · KeyError: 'Column not found: revenue'", "err"),
            ("•", "app", "repair_routed · Executor → Coder · attempt 1", "ev"),
            ("•", "selector", "speaker_selected → Coder", "ev"),
        ],
        tab="Code",
        body=f'<pre class="code">{FIXED_CODE}</pre>',
        outcome=(
            "run",
            "Coder is repairing from the real error",
            "Revision 2 will replace the failing line; it appears here when the Coder message arrives.",
        ),
        facts=(1, 0, 0, "3,010 / 1,377"),
        fault=False,
    ),
    "reviewer-feedback": dict(
        label="Reviewer feedback",
        count=6,
        cells=["on", "on", "err", "on", "ok", "warn"],
        run_chip=("Reviewer feedback", "warn"),
        mode="Guarded selector",
        nodes=IDLE
        | {
            "Planner": S("done", "DONE"),
            "Coder": S("active", "REVISING"),
            "Executor": S("ok", "OK · EXIT 0"),
            "Reviewer": S("feedback", "FEEDBACK · 2 ISSUES"),
            "Human": S("idle", "NOT STARTED"),
        },
        edges={
            "p_c": "used",
            "c_e": "done-ok",
            "e_r": "used",
            "repair": "used",
            "feedback": "feedback",
        },
        feed=[
            ("3", "Executor", "exec_result · error · KeyError", "err"),
            ("4", "Coder", "revision 2 · derives revenue", ""),
            ("5", "Executor", "exec_result · ok · 2 charts, results.json", "ok"),
            ("6", "Reviewer", "review_feedback · 2 issues", "fb"),
            ("•", "selector", "speaker_selected → Coder", "ev"),
        ],
        tab="Reviewer",
        body=f'<pre class="code" style="white-space:pre-wrap;color:#ffe2a8">{escape(REVIEW_FB)}</pre>',
        outcome=(
            "run",
            "Reviewer returned feedback to the Coder",
            "The Reviewer cannot approve this revision; the Coder must fix and re-execute.",
        ),
        facts=(1, 1, 0, "5,412 / 2,150"),
        fault=False,
    ),
    "approved": dict(
        label="Reviewer approved",
        count=9,
        cells=["on", "on", "err", "on", "ok", "warn", "on", "ok", "ok"],
        run_chip=("Reviewer approved · 9/12", "ok"),
        mode="Guarded selector",
        nodes=IDLE
        | {
            "Planner": S("done", "DONE"),
            "Coder": S("done", "DONE"),
            "Executor": S("ok", "OK · EXIT 0"),
            "Reviewer": S("approved", "APPROVED · MSG 9"),
            "Human": S("pending", "PENDING DECISION"),
        },
        edges={
            "p_c": "used",
            "c_e": "done-ok",
            "e_r": "done-ok",
            "r_h": "flow",
            "repair": "used",
            "feedback": "used",
        },
        feed=[
            ("7", "Coder", "revision 3 · axis labels + offset note", ""),
            ("8", "Executor", "exec_result · ok", "ok"),
            ("9", "Reviewer", "APPROVED", "ok"),
            ("•", "app", "reviewer_approved · message 9", "ev"),
            ("•", "app", "terminated · REVIEWER_APPROVED", "ev"),
        ],
        tab="Reviewer",
        body=f'<pre class="code" style="white-space:pre-wrap;color:#b9f3d3">{escape(APPROVE_TXT)}</pre>',
        outcome=(
            "ok",
            "Reviewer approved on message 9 of 12",
            "Human approval is a separate step in Insights Studio. Nothing is final until you decide.",
        ),
        facts=(1, 1, 0, "7,904 / 3,011"),
        fault=False,
    ),
    "limit-reached": dict(
        label="Limit reached",
        count=12,
        cells=["on", "on", "err", "on", "err", "on", "ok", "warn", "on", "err", "on", "ok"],
        run_chip=("Unapproved · limit 12/12", "bad"),
        mode="Guarded selector",
        nodes=IDLE
        | {
            "Planner": S("done", "DONE"),
            "Coder": S("done", "DONE"),
            "Executor": S("ok", "LAST EXEC OK"),
            "Reviewer": S("feedback", "NEVER APPROVED"),
            "Human": S("terminal", "RUN UNAPPROVED"),
        },
        edges={"p_c": "used", "c_e": "used", "e_r": "used", "repair": "used", "feedback": "used"},
        feed=[
            ("10", "Executor", "exec_result · error · ValueError", "err"),
            ("11", "Coder", "revision 5", ""),
            ("12", "Executor", "exec_result · ok (not reviewed)", "ok"),
            ("•", "app", "limit_reached · count 12", "ev"),
            ("•", "app", "terminated · LIMIT_REACHED", "ev"),
        ],
        tab="Output",
        body='<div class="body"><span class="chip bad"><i class="dot"></i>UNAPPROVED</span><p class="muted" style="margin:10px 0 0">The 12-message budget was used before the Reviewer approved. Results are shown labelled <b>Unapproved</b> and are never presented as verified.</p></div>',
        outcome=(
            "bad",
            "Stopped at 12/12 — not approved by the Reviewer",
            "You can ask a follow-up (new run, fresh budget) or inspect the partial work.",
        ),
        facts=(3, 2, 0, "13,870 / 5,402"),
        fault=False,
    ),
    "fault-injection": dict(
        label="Fault injection (test)",
        count=4,
        cells=["on", "on", "err", "on"],
        run_chip=("Repairing · attempt 1", "warn"),
        mode="Guarded selector",
        nodes=IDLE
        | {
            "Planner": S("done", "DONE"),
            "Coder": S("active", "REPAIRING · ATTEMPT 1"),
            "Executor": S("error", "ERROR · EXIT 1"),
            "Human": S("idle", "NOT STARTED"),
        },
        edges={"p_c": "used", "c_e": "used", "repair": "repair"},
        feed=[
            (
                "•",
                "test_harness",
                "test_fault_injected · column 'units' renamed in Coder output (TEST ONLY)",
                "ev",
            ),
            ("2", "Coder", "code_generated · (mutated by harness)", ""),
            ("3", "Executor", "exec_result · error · AttributeError: no attribute 'units'", "err"),
            ("•", "app", "repair_routed · attempt 1", "ev"),
            ("4", "Coder", "repair in progress…", ""),
        ],
        tab="Error",
        body=f'<pre class="code">{FAULT_CODE}</pre><pre class="err">{FAULT_ERR}</pre>',
        outcome=(
            "bad",
            "TEST FAULT INJECTED — not a natural error",
            "The Coder is repairing from the real stderr. This run is labelled test-only everywhere.",
        ),
        facts=(1, 0, 0, "3,150 / 1,402"),
        fault=True,
    ),
}
STATE_ORDER = list(STATES)

# One row per counted agent message, in order (a prefix of this is shown per state).
LEDGER_FULL = [
    ("Planner", "agent_message", "Plan: 5 steps (revenue, group, compare, split, charts)", ""),
    ("Coder", "code_generated", "analysis.py v1 · 23 lines", ""),
    ("Executor", "exec_result", "error · exit 1 · KeyError: revenue", "bad"),
    ("Coder", "code_generated", "analysis.py v2 · derives revenue column", ""),
    ("Executor", "exec_result", "ok · exit 0 · 2 charts + results.json", "ok"),
    ("Reviewer", "review_feedback", "2 issues: axis unit, offset note", "warn"),
    ("Coder", "code_generated", "analysis.py v3 · labels + note", ""),
    ("Executor", "exec_result", "ok · exit 0", "ok"),
    ("Reviewer", "reviewer_approved", "APPROVED", "ok"),
]
LEDGER_LIMIT = [
    ("Planner", "agent_message", "Plan: 5 steps", ""),
    ("Coder", "code_generated", "v1", ""),
    ("Executor", "exec_result", "error · KeyError: revenue", "bad"),
    ("Coder", "code_generated", "v2", ""),
    ("Executor", "exec_result", "error · TypeError: unsupported operand", "bad"),
    ("Coder", "code_generated", "v3", ""),
    ("Executor", "exec_result", "ok · exit 0", "ok"),
    ("Reviewer", "review_feedback", "3 issues", "warn"),
    ("Coder", "code_generated", "v4", ""),
    ("Executor", "exec_result", "error · ValueError", "bad"),
    ("Coder", "code_generated", "v5", ""),
    ("Executor", "exec_result", "ok · exit 0 (not reviewed)", "ok"),
]
LEDGER_FAULT = [
    ("Planner", "agent_message", "Plan: 5 steps", ""),
    ("Coder", "code_generated", "v1 · mutated by test harness (TEST FAULT)", "warn"),
    ("Executor", "exec_result", "error · AttributeError: no attribute 'units'", "bad"),
    ("Coder", "agent_message", "repair in progress", ""),
]


def ledger_html(key: str, count: int) -> str:
    seq = (
        LEDGER_LIMIT
        if key == "limit-reached"
        else LEDGER_FAULT
        if key == "fault-injection"
        else LEDGER_FULL
    )
    rows = ""
    for i in range(12):
        if i < count and i < len(seq):
            a, ev, out, k = seq[i]
            mark = {
                "bad": '<span class="ic bad">✕</span>',
                "ok": '<span class="ic ok">✓</span>',
                "warn": '<span class="ic warn">!</span>',
            }.get(k, '<span class="ic"></span>')
            rows += f'<tr><td class="r num">{i + 1}</td><td>{a}</td><td class="mono">{ev}</td><td>{mark} {escape(out)}</td></tr>'
        else:
            rows += f'<tr><td class="r num muted">{i + 1}</td><td class="muted" colspan="3">— not used</td></tr>'
    return (
        f'<section class="pane" aria-label="Message ledger"><header>Message ledger · {count} of 12 used'
        f'<span class="sp"></span><span>task message and events are not counted</span></header>'
        f'<div class="tscroll"><table class="t"><thead><tr><th class="r">#</th><th>Agent</th><th>Event</th><th>Outcome</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div></section>"
    )


def livewire(key: str) -> str:
    s = STATES[key]
    nav = "".join(
        f'<a href="livewire-{k}.html" class="{"on" if k == key else ""}">{STATES[k]["label"]}</a>'
        for k in STATE_ORDER
    )
    rep, fbk, _, tok = s["facts"]
    kind = s["outcome"][0]
    toolbar = (
        COMMON_TB
        + chip(s["run_chip"][0], s["run_chip"][1])
        + (chip("TEST FAULT INJECTED", "test") if s["fault"] else "")
        + f'<span class="counter" title="Real agent messages (max 12)"><span class="n num">{s["count"]}/12</span>{cells(s["cells"])}</span>'
    )
    body = f"""<div class="state-nav" aria-label="Mockup states (design review only)">{nav}</div>
<main class="canvas lw">
<section class="pane" aria-label="Agent workflow"><header>Agent workflow · {s["mode"]}<span class="sp"></span><span>Every motion = one real event</span></header>
<div class="body">{flow_svg(s["nodes"], s["edges"], s["fault"])}</div></section>
<div class="lw-grid">
<section class="pane feed" aria-label="Message feed" aria-live="polite"><header>Live feed · runtime events</header>
{feed_html(s["feed"]) or '<div class="body muted">Waiting for the first event.</div>'}</section>
<section class="pane" aria-label="Inspector"><div class="tabs"><span class="{"on" if s["tab"] == "Plan" else ""}">Plan</span><span class="{"on" if s["tab"] == "Code" else ""}">Code</span><span class="{"on" if s["tab"] in ("Output", "Error") else ""}">Output / stderr</span><span class="{"on" if s["tab"] == "Reviewer" else ""}">Reviewer</span><span>Tokens</span></div>
{s["body"]}</section>
<aside class="pane" aria-label="Run facts"><header>Run facts</header><div class="body">
<div class="outcome {kind}" style="margin-bottom:12px"><b>{s["outcome"][1]}</b>{s["outcome"][2]}</div>
<dl class="kv">
<dt>Messages</dt><dd>{s["count"]} / 12</dd><dt>Repair attempts</dt><dd>{rep}</dd><dt>Reviewer rounds</dt><dd>{fbk}</dd>
<dt>Tokens in / out</dt><dd>{tok}</dd><dt>Cost</dt><dd>Pricing not configured</dd>
<dt>Reviewer</dt><dd>{"Approved" if key == "approved" else "Unapproved" if key == "limit-reached" else "Pending"}</dd><dt>Human</dt><dd>{"Pending" if key == "approved" else "—"}</dd>
</dl></div></aside>
</div>
{ledger_html(key, s["count"])}</main>"""
    return shell(
        "live", "Agent Livewire", toolbar, body, f"DataPilot — Livewire: {s['label']} (mockup)"
    )


# --------------------------------------------------------------------------- Insights Studio
def hbar(
    items: list[tuple[str, float]], title: str, xlabel: str, highlight: str, w: int = 1000
) -> str:
    rowh, left, right, top, room = (34, 96, 16, 40, 78) if w > 500 else (34, 66, 4, 40, 54)
    h = top + rowh * len(items) + 44
    neg = max([-v for _, v in items if v < 0] or [0.0])
    pos = max([v for _, v in items if v > 0] or [0.0])
    scale = (w - left - right - 2 * room) / (neg + pos)
    zero = left + room + neg * scale
    lo, hi = zero - neg * scale - room, zero + pos * scale + room
    g = [f'<text class="t" x="0" y="16">{escape(title)}</text>']
    step = (2e6 if (neg + pos) > 5e6 else 0.5e6) * (2 if w <= 500 else 1)
    t = -(neg // step) * step - (step if neg % step else 0) + 0.0
    while t <= pos + step:
        x = zero + t * scale
        if lo <= x <= hi:
            g.append(
                f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{top - 8}" y2="{h - 36}"/>'
                f'<text x="{x:.1f}" y="{h - 20}" text-anchor="middle">{t / 1e6:+.1f}</text>'
            )
        t += step
    for i, (name, v) in enumerate(items):
        y = top + i * rowh
        wbar = abs(v) * scale
        x = zero if v >= 0 else zero - wbar
        cls = "posb" if v >= 0 else ("neg" if name == highlight else "dim")
        ax = (x + wbar + 6) if v >= 0 else (x - 6)
        g.append(
            f'<text x="{left - 8}" y="{y + 19}" text-anchor="end">{escape(name)}</text>'
            f'<rect class="{cls}" x="{x:.1f}" y="{y + 4}" width="{wbar:.1f}" height="20" rx="1"/>'
            f'<text class="ann" x="{ax:.1f}" y="{y + 19}" text-anchor="{"start" if v >= 0 else "end"}">{m(v, True)}</text>'
        )
    g.append(
        f'<line class="axis" x1="{zero:.1f}" x2="{zero:.1f}" y1="{top - 8}" y2="{h - 36}"/>'
        f'<text x="{(lo + hi) / 2:.0f}" y="{h - 4}" text-anchor="middle">{escape(xlabel)}</text>'
    )
    return f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">{"".join(g)}</svg>'


def columns(title: str, ylabel: str, w: int = 1000) -> str:
    h, left, bottom, top = 260, 56, 40, 40
    vals = list(monthly.items())
    mx = 70e6
    bw = 110 if w > 500 else 48
    g = [f'<text class="t" x="0" y="16">{escape(title)}</text>']
    for t in (0, 20e6, 40e6, 60e6):
        y = h - bottom - (h - bottom - top) * t / mx
        g.append(
            f'<line class="grid" x1="{left}" x2="{w - 10}" y1="{y:.1f}" y2="{y:.1f}"/>'
            f'<text x="{left - 6}" y="{y + 4:.1f}" text-anchor="end">{t / 1e6:.0f}</text>'
        )
    step = (w - left - 10) / len(vals)
    for i, (k, v) in enumerate(vals):
        bh = (h - bottom - top) * v / mx
        x = left + i * step + (step - bw) / 2
        cls = "neg" if k == "2026-09" else "dim"
        g.append(
            f'<rect class="{cls}" x="{x:.1f}" y="{h - bottom - bh:.1f}" width="{bw}" height="{bh:.1f}" rx="1"/>'
            f'<text class="ann" x="{x + bw / 2:.1f}" y="{h - bottom - bh - 6:.1f}" text-anchor="middle">{v / 1e6:.1f}</text>'
            f'<text x="{x + bw / 2:.1f}" y="{h - bottom + 16}" text-anchor="middle">{k if w > 500 else k[5:]}</text>'
        )
    g.append(
        f'<line class="axis" x1="{left}" x2="{w - 10}" y1="{h - bottom}" y2="{h - bottom}"/>'
        f'<text x="12" y="{(top + h - bottom) / 2:.0f}" transform="rotate(-90 12 {(top + h - bottom) / 2:.0f})" text-anchor="middle">{escape(ylabel)}</text>'
    )
    return f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">{"".join(g)}</svg>'


def dual(fn, *args, wide: int, **kw) -> str:
    """Wide variant for desktop, narrow (1:1 at 390px) variant for mobile; CSS swaps them."""
    narrow = 340
    return f'<div class="cw">{fn(*args, **kw, w=wide)}</div><div class="cn">{fn(*args, **kw, w=narrow)}</div>'


def insights() -> str:
    rows = "".join(
        f'<tr><td>{c}</td><td class="r">{m(cat.loc[c, "2026-08"])}</td><td class="r">{m(cat.loc[c, "2026-09"])}</td>'
        f'<td class="r {"neg" if v < 0 else "pos"}">{m(v, True)}</td><td class="r {"neg" if v < 0 else "pos"}">{v / cat.loc[c, "2026-08"] * 100:+.1f}%</td></tr>'
        for c, v in cat_change.items()
    )
    toolbar = (
        COMMON_TB
        + chip("Reviewer: Approved · 9/12", "ok")
        + chip("Human: Pending", "info")
        + chip("Pricing not configured", "warn", "hide-m")
    )
    body = f"""<div class="is-head">
<div class="q">Question · Which category had the biggest revenue drop in September vs August, and which region caused most of it?</div>
<p class="answer">{top_cat} fell the most, down <em>{m(TOP_DROP)}</em> from August to September, driven by <em>{TOP_REG}</em> ({m(TOP_REG_VAL)}), partly offset by growth in the other regions.</p>
<span class="chip ok"><i class="dot"></i>Reviewer approved</span> <span class="chip info"><i class="dot"></i>Human approval pending</span> <span class="chip"><i class="dot"></i>12,480 rows analysed</span>
</div>
<div class="strip" aria-label="Key figures">
<div><div class="l">Sep revenue</div><div class="v num">{m(SEP)}</div><div class="d neg">{SEP_PCT:+.1f}% vs Aug</div></div>
<div><div class="l">Aug revenue</div><div class="v num">{m(AUG)}</div><div class="d muted">baseline</div></div>
<div><div class="l">Largest category drop</div><div class="v num neg">{m(TOP_DROP, True)}</div><div class="d muted">{top_cat}</div></div>
<div><div class="l">Main regional cause</div><div class="v num neg">{m(TOP_REG_VAL, True)}</div><div class="d muted">{TOP_REG} · within {top_cat}</div></div>
<div><div class="l">Offset elsewhere</div><div class="v num pos">{m(OFFSET, True)}</div><div class="d muted">other regions</div></div>
</div>
<main class="canvas">
<div class="vgrid">
<section class="pane chart c7" aria-label="Category change"><header>Chart 1 · category<span class="sp"></span><span>Sep vs Aug</span></header>
<div class="body">{dual(hbar, list(cat_change.items()), "Revenue change by category", "Revenue change (₹ million)", top_cat, wide=1000)}</div>
<div class="chart-note">Source: results.json → charts[0] · rendered from verified output</div></section>
<section class="pane chart c5" aria-label="Region contribution"><header>Chart 2 · region<span class="sp"></span><span>drill-down: {top_cat}</span></header>
<div class="body">{dual(hbar, list(reg_change.items()), f"{top_cat}: change by region", "Revenue change (₹ million)", TOP_REG, wide=700)}</div></section>
<section class="pane chart c7" aria-label="Monthly revenue"><header>Chart 3 · context<span class="sp"></span><span>Jun–Sep</span></header>
<div class="body">{dual(columns, "Revenue by month", "Revenue (₹ million)", wide=1000)}</div></section>
<section class="pane narr c5" aria-label="Narrative"><header>Analyst narrative<span class="sp"></span><span class="muted">AI-generated · checked by Reviewer</span></header>
<div class="body"><p>Total revenue fell {abs(SEP_PCT):.1f}% from August to September. {top_cat} accounts for the largest category decline at {m(TOP_DROP)}.</p>
<p>Inside {top_cat}, <b>{TOP_REG}</b> fell {m(TOP_REG_VAL)}, while the other three regions together grew {m(OFFSET)}.</p>
<p class="src">Every figure above appears in results.json or stdout. Method: revenue = units × unit_price × (1 − discount).</p>
<div class="eyebrow" style="margin:14px 0 6px">How it was verified · from the event log</div>
<div class="flag"><span class="ic bad">✕</span><span>Execution 1 failed: <span class="mono">KeyError: revenue</span> → Coder repaired from the real error</span></div>
<div class="flag"><span class="ic warn">!</span><span>Reviewer asked for axis units and an offset note → Coder revised</span></div>
<div class="flag"><span class="ic ok">✓</span><span>Execution 3 exit 0 · numbers match results.json · Reviewer APPROVED (msg 9/12)</span></div>
<div class="flag"><span class="ic info">i</span><span>analysis.py re-run twice → identical results hash</span></div></div></section>
<section class="pane c8" aria-label="Detail table"><header>Category detail<span class="sp"></span><span>sortable</span></header>
<div class="tscroll"><table class="t"><thead><tr><th>Category</th><th class="r">August</th><th class="r">September</th><th class="r">Change</th><th class="r">%</th></tr></thead><tbody>{rows}</tbody></table></div></section>
<section class="pane c4" aria-label="Verification and exports"><header>Verification &amp; exports</header><div class="body">
<div class="verify">
<div class="row"><span class="muted">Reviewer</span><span class="chip ok"><i class="dot"></i>Approved on msg 9</span></div>
<div class="row"><span class="muted">Execution</span><span>2 errors repaired · final exit 0</span></div>
<div class="row"><span class="muted">Human</span><span class="chip info"><i class="dot"></i>Pending</span></div>
</div>
<div style="margin-top:12px">
<div class="art"><span>analysis.py</span><span class="sp"></span><span class="muted mono">Python</span><span class="btn">Download</span></div>
<div class="art"><span>revenue_change_by_category.png</span><span class="sp"></span><span class="btn">PNG</span></div>
<div class="art"><span>datapilot_report.pdf</span><span class="sp"></span><span class="muted">1 page</span><span class="btn">PDF</span></div>
</div></div></section>
</div>
<section class="pane" aria-label="Decision and follow-up">
<div class="approval"><b>Your decision</b><span class="muted">Reviewer approval does not finalize the report.</span><span class="sp"></span>
<span class="btn danger">Reject</span><span class="btn ok">Approve report</span></div>
<div class="body"><div class="followup"><div class="in">Ask a follow-up in this session, e.g. “Which South products fell most?”</div><span class="btn primary">Ask follow-up</span></div>
<div class="muted" style="font-size:11px;margin-top:6px">A follow-up starts a new run with a fresh 12-message budget and keeps this dataset and history.</div></div></section>
</main>"""
    return shell("ins", "Insights Studio", toolbar, body, "DataPilot — Insights Studio (mockup)")


# --------------------------------------------------------------------------- tokens / contrast
def lum(hex_: str) -> float:
    c = [int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a: str, b: str) -> float:
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


TOKENS = [
    ("--bg", "#0b1426", "Midnight navy · page"),
    ("--surface", "#121c30", "Graphite · panes"),
    ("--surface-2", "#1a2640", "Slate · raised / selected"),
    ("--line", "#26324a", "Hairline"),
    ("--accent", "#19c3b1", "Electric teal · primary"),
    ("--accent-2", "#3b82f6", "Blue · info / data"),
    ("--text", "#f4f1e8", "Ivory · text"),
    ("--muted", "#9aa7bd", "Muted text"),
    ("--ok", "#3dd68c", "Verified / success"),
    ("--warn", "#f5b84b", "Feedback / warning"),
    ("--danger", "#f0556a", "Error / unapproved"),
]
PAIRS = [
    ("--text", "#f4f1e8", "--bg", "#0b1426", 4.5),
    ("--text", "#f4f1e8", "--surface", "#121c30", 4.5),
    ("--muted", "#9aa7bd", "--surface", "#121c30", 4.5),
    ("--muted", "#9aa7bd", "--bg", "#0b1426", 4.5),
    ("--accent", "#19c3b1", "--surface", "#121c30", 3.0),
    ("--accent-ink", "#04201d", "--accent", "#19c3b1", 4.5),
    ("--ok", "#3dd68c", "--surface", "#121c30", 3.0),
    ("--warn", "#f5b84b", "--surface", "#121c30", 3.0),
    ("--danger", "#f0556a", "--surface", "#121c30", 3.0),
    ("#ff8a9a (neg text)", "#ff8a9a", "--surface", "#121c30", 4.5),
    ("--accent-2", "#3b82f6", "--surface", "#121c30", 3.0),
]
MAP = [
    ("Idle · armed", "(none yet)", "All nodes idle, counter 0/12, empty feed"),
    (
        "Planner done · Coder active",
        "run_started, agent_message(Planner), speaker_selected(Coder)",
        "Planner DONE, Coder pulse, p→c edge used, counter 1/12",
    ),
    (
        "Execution error",
        "exec_started, exec_result(status≠ok), agent_message(Executor)",
        "Executor error state, red feed row, stderr in inspector, cell turns red",
    ),
    (
        "Repair",
        "repair_routed (derived from observed next speaker = Coder)",
        "Animated red edge Executor→Coder once, “attempt n”, Coder REPAIRING",
    ),
    (
        "Reviewer feedback",
        "review_feedback (Reviewer message ≠ approval)",
        "Amber edge Reviewer→Coder once, Reviewer FEEDBACK, text in inspector",
    ),
    (
        "Reviewer approved",
        "reviewer_approved (source Reviewer, last exec ok), terminated",
        "Reviewer APPROVED, Human node PENDING; terminal",
    ),
    (
        "Limit reached",
        "limit_reached (count = 12, no valid approval), terminated",
        "Terminal “Unapproved · limit 12/12”; never styled as verified",
    ),
    (
        "Fault injection (test only)",
        "test_fault_injected (test harness)",
        "Persistent TEST FAULT INJECTED badge on Coder + toolbar chip; manifest flag",
    ),
    (
        "Human approved / rejected",
        "human_approved / human_rejected",
        "Human node state only; independent of the Reviewer node",
    ),
]


def tokens_page() -> str:
    sw = "".join(
        f'<div><i style="background:{h}"></i><span><b>{n}</b><br>{h} · <span class="muted">{d}</span></span></div>'
        for n, h, d in TOKENS
    )
    rows = "".join(
        f'<tr><td>{fn}</td><td>{bn}</td><td class="r num">{ratio(fh, bh):.2f}:1</td><td class="r">{need:g}:1</td>'
        f"<td>{'<span class=pos>PASS</span>' if ratio(fh, bh) >= need else '<span class=neg>FAIL</span>'}</td></tr>"
        for fn, fh, bn, bh, need in PAIRS
    )
    mp = "".join(f"<tr><td>{a}</td><td class='mono'>{b}</td><td>{c}</td></tr>" for a, b, c in MAP)
    body = f"""<main class="canvas"><section class="pane"><header>Colour tokens</header><div class="body"><div class="sw">{sw}</div></div></section>
<section class="pane"><header>Contrast check (WCAG 2.1, computed)</header><div class="tscroll"><table class="t"><thead><tr><th>Foreground</th><th>Background</th><th class="r">Ratio</th><th class="r">Needed</th><th>Result</th></tr></thead><tbody>{rows}</tbody></table></div></section>
<section class="pane"><header>Type, space, shape</header><div class="body">
<div class="kv" style="grid-template-columns:140px 1fr;text-align:left"><dt>Family</dt><dd style="text-align:left">Segoe UI / system UI stack; Cascadia Mono / Consolas for code</dd>
<dt>Scale</dt><dd style="text-align:left">11 · 12 · 13 (body) · 15 · 22 (title) · 26 (KPI, tabular numerals)</dd>
<dt>Spacing</dt><dd style="text-align:left">12 px gap, 14 px pane padding (12 px on mobile)</dd>
<dt>Shape</dt><dd style="text-align:left">3 px radius, 1 px hairlines; no shadows, no card grids</dd>
<dt>Status</dt><dd style="text-align:left">Colour is always paired with a text label or icon</dd>
<dt>Motion</dt><dd style="text-align:left">Edge flow + node pulse only on real events; disabled under prefers-reduced-motion</dd>
<dt>Breakpoints</dt><dd style="text-align:left">≥1400 · 1024–1399 · 768–1023 · &lt;768 (rail becomes bottom tabs)</dd></div></div></section>
<section class="pane"><header>Livewire state → RuntimeEvent mapping</header><div class="tscroll"><table class="t"><thead><tr><th>Visual state</th><th>Real source event(s)</th><th>What the UI shows</th></tr></thead><tbody>{mp}</tbody></table></div></section>
</main>"""
    return shell("ask", "Design tokens", COMMON_TB, body, "DataPilot — Design tokens (mockup)")


def index_page() -> str:
    shots = [("ask-explore", "Ask & Explore"), ("insights-studio", "Insights Studio")] + [
        (f"livewire-{k}", f"Livewire · {STATES[k]['label']}") for k in STATE_ORDER
    ]
    figs = "".join(
        f'<figure><a href="{p}.html"><img src="png/{p}-1920.png" alt="{n} at 1920px" loading="lazy"></a>'
        f'<figcaption>{n} · 1920 px · <a href="png/{p}-390.png">390 px PNG</a> · <a href="{p}.html">live HTML</a></figcaption></figure>'
        for p, n in shots
    )
    body = (
        f'<main class="canvas"><section class="pane"><header>Mockup gallery</header><div class="body"><div class="gal">{figs}</div>'
        '<p class="muted">Design tokens: <a href="tokens.html">tokens.html</a> · resize the browser to see responsive behaviour.</p></div></section></main>'
    )
    return shell("ask", "Mockup gallery", COMMON_TB, body, "DataPilot — Mockup gallery")


def main() -> None:
    pages = {
        "ask-explore": ask_explore(),
        "insights-studio": insights(),
        "tokens": tokens_page(),
        "index": index_page(),
    }
    pages |= {f"livewire-{k}": livewire(k) for k in STATE_ORDER}
    for name, html in pages.items():
        (HERE / f"{name}.html").write_text(html, encoding="utf-8")
    print(f"built {len(pages)} pages")  # noqa: T201


if __name__ == "__main__":
    main()

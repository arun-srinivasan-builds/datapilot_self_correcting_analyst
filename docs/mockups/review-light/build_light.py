"""Builds the LIGHT-theme mockups into review-light/pages (design only; not Streamlit code).

Data, agent copy, charts and state definitions are shared with the dark iteration (../build.py);
shell, layout and styling are new. The dark mockups are left untouched.

    .venv\\Scripts\\python docs/mockups/review-light/build_light.py
"""

from __future__ import annotations

import copy
import re
import sys
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGES = HERE / "pages"
sys.path.insert(0, str(HERE.parent))
import build as d  # noqa: E402  (dark iteration: data, copy, chart + ledger builders)

CSS = "light.css"
MID = "·"

# --------------------------------------------------------------------------- shell
ICON = d.ICON


def shell(active: str, crumb: str, toolbar: str, body: str, title: str) -> str:
    navs = ""
    for k, label, href in d.NAV:
        cur = ' is-active" aria-current="page' if k == active else ""
        short = label.split(" ")[-1]
        navs += f'<a class="nav{cur}" href="{href}" aria-label="{label}">{ICON[k]}<span>{short}</span></a>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><link rel="stylesheet" href="{CSS}"></head>
<body><div class="app">
<nav class="rail" aria-label="Workspaces"><div class="logo" aria-hidden="true">D</div>{navs}<div class="grow"></div></nav>
<div class="main">
<header class="toolbar"><div class="crumb">DataPilot <span>/ {escape(crumb)}</span></div><div class="sp"></div>{toolbar}</header>
{body}
</div></div></body></html>"""


chip = d.chip
COMMON_TB = (
    chip("sales_sample.csv · 12,480 rows", "info", "hide-m")
    + chip("gpt-6-luna", "live", "hide-m")
    + '<span class="mock-flag">DESIGN MOCKUP · representative data</span>'
)

df, cat, cat_change, reg_change = d.df, d.cat, d.cat_change, d.reg_change
m = d.m


# --------------------------------------------------------------------------- Ask & Explore
def profile_rows() -> str:
    rows = []
    n = len(df)
    for col in ["order_date", "region", "category", "product", "units", "unit_price", "discount"]:
        s = df[col]
        nulls = int(s.isna().sum())
        comp = 100 * (n - nulls) / n
        if col == "order_date":
            typ, rng = "datetime", f"{s.min()} → {s.max()}"
        elif s.dtype.kind in "if":
            typ = "integer" if s.dtype.kind == "i" else "float"
            rng = f"{s.min():g} – {s.max():g}"
        else:
            typ = "text"
            rng = ", ".join(sorted(s.unique())[:3]) + " …"
        health = (
            '<span class="health ok">✓ Complete</span>'
            if nulls == 0
            else f'<span class="health warn">! {100 - comp:.1f}% missing</span>'
        )
        rows.append(
            f"<tr><td><b>{col}</b></td><td>{typ}</td>"
            f'<td><div class="bar"><i style="width:{comp:.0f}%"></i></div></td><td>{health}</td>'
            f'<td class="r">{s.nunique():,}</td><td>{escape(rng)}</td></tr>'
        )
    return "".join(rows)


def ask_explore() -> str:
    cols = ["order_date", "region", "category", "product", "units", "unit_price", "discount"]
    num = {"units", "unit_price", "discount"}
    head = "".join(f'<th class="{"r" if c in num else ""}">{c}</th>' for c in cols)
    body_rows = "".join(
        "<tr>"
        + "".join(
            f'<td class="{"r" if c in num else ""}">{escape(str(v))}</td>'
            for c, v in zip(cols, row, strict=True)
        )
        + "</tr>"
        for row in df.head(10)[cols].itertuples(index=False)
    )
    body = f"""<div class="strip" aria-label="Dataset profile">
<div><div class="l">Rows</div><div class="v num">12,480</div><div class="d">1 sheet · CSV</div></div>
<div><div class="l">Columns</div><div class="v num">7</div><div class="d">4 text · 3 numeric</div></div>
<div><div class="l">Missing values</div><div class="v num">0</div><div class="d pos">✓ none detected</div></div>
<div><div class="l">Date column</div><div class="v" style="font-size:20px">order_date</div><div class="d">2026-06-01 → 2026-09-30</div></div>
<div><div class="l">Duplicates</div><div class="v num">0</div><div class="d pos">✓ clean</div></div>
</div>
<main class="canvas ae">
<section class="pane" aria-label="Data source"><header><span class="step">1</span>Data source</header><div class="body">
<div class="drop"><b>Drop CSV or XLSX</b>or browse · up to 25 MB</div>
<ul class="list" style="margin-top:12px">
<li class="sel"><span class="ic ok">●</span><span>sales_sample.csv</span><span class="sp"></span><span class="muted num">12,480</span></li>
<li><span class="ic info">○</span><span>sales_alt_schema.csv</span><span class="sp"></span><span class="muted num">3,210</span></li>
<li><span class="ic info">○</span><span>multisheet.xlsx</span><span class="sp"></span><span class="muted">3 sheets</span></li>
</ul>
<div class="field" style="margin-top:14px"><label>Sheet</label><div class="select"><span>Orders</span><span class="muted">▾</span></div></div>
<div class="muted" style="font-size:11px;margin-top:-4px">CSV has one sheet; XLSX lets you pick.</div>
</div></section>

<section class="pane" aria-label="Profile and preview"><header><span class="step">2</span>Profile &amp; preview<span class="sp"></span><span>sales_sample.csv</span></header>
<div class="qsum"><span class="chip ok"><i class="dot"></i>Schema readable</span><span class="chip ok"><i class="dot"></i>No missing values</span>
<span class="chip ok"><i class="dot"></i>No duplicate rows</span><span class="chip info"><i class="dot"></i>Date column: order_date</span></div>
<div class="tscroll"><table class="t"><thead><tr><th>Column</th><th>Type</th><th>Completeness</th><th>Quality</th><th class="r">Unique</th><th>Range / samples</th></tr></thead>
<tbody>{profile_rows()}</tbody></table></div>
<header style="border-top:1px solid var(--line)">Preview · first 10 of 12,480 rows</header>
<div class="tscroll"><table class="t"><thead><tr>{head}</tr></thead><tbody>{body_rows}</tbody></table></div></section>

<aside class="pane" aria-label="Ask a question"><header><span class="step">3</span>Ask<span class="sp"></span><span class="seg"><span class="on">Guarded</span><span>Round-robin</span></span></header>
<div class="body">
<div class="field"><label for="q">Your question</label>
<textarea id="q" class="q" readonly>Which category had the biggest revenue drop in September vs August, and which region caused most of it?</textarea></div>
<div style="display:flex;gap:10px;align-items:center"><span class="btn primary">Run analysis</span><span class="muted" style="font-size:12px">Up to 12 agent messages</span></div>
<div class="field" style="margin-top:18px"><label>Suggested from this dataset</label></div>
<div class="sugg">
<div>Revenue by month and category</div>
<div>Top 5 products by revenue in September</div>
<div>Does a higher discount raise units sold?</div>
</div>
<div class="field" style="margin-top:18px"><label>Session history</label></div>
<div class="hist"><div><span class="ic ok">✓</span><span>Biggest drop Sep vs Aug · <span class="muted">Reviewer approved · 9/12</span></span></div>
<div><span class="ic warn">!</span><span>Revenue by region · <span class="muted">Unapproved · 12/12</span></span></div></div>
</div></aside>
</main>"""
    tb = COMMON_TB + chip("Pricing not configured", "warn", "hide-m") + chip("Idle", "", "")
    return shell("ask", "Ask & Explore", tb, body, "DataPilot — Ask & Explore (light mockup)")


# --------------------------------------------------------------------------- Livewire
GLYPH = {
    "active": "▶ ",
    "ok": "✓ ",
    "error": "✕ ",
    "feedback": "! ",
    "approved": "✓ ",
    "pending": "◌ ",
    "terminal": "✕ ",
    "waiting": "⋯ ",
    "done": "✓ ",
    "idle": "",
}


def flow_svg(st: dict, edges: dict, fault: bool) -> str:
    def node(name: str, x: int, y: int, w: int, h: int) -> str:
        status, label = st[name]
        extra = ""
        if name == "Coder" and fault:
            extra = (
                f'<g class="badge-fault"><rect x="{x}" y="{y - 22}" width="{w}" height="18" rx="2"/>'
                f'<text x="{x + w / 2}" y="{y - 9}" text-anchor="middle">TEST FAULT INJECTED</text></g>'
            )
        return (
            f'<g class="node is-{status}"><rect class="body" x="{x}" y="{y}" width="{w}" height="{h}" rx="3"/>'
            f'<rect class="sbar" x="{x}" y="{y}" width="5" height="{h}" rx="1"/>'
            f'<text x="{x + 16}" y="{y + 26}">{name}</text><text class="sub" x="{x + 16}" y="{y + 44}">{d.NODE_SUB[name]}</text>'
            f'<text class="st" x="{x + 16}" y="{y + h - 10}">{GLYPH.get(status, "")}{escape(label)}</text>{extra}</g>'
        )

    labels: list[str] = []

    def e(
        name: str,
        path: str,
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
        return f'<path class="edge {cls}" d="{path}" marker-end="url(#a)"/>'

    defs = (
        '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0 0L10 5L0 10z" fill="#6b7a8c"/></marker></defs>'
    )
    hz = [defs]
    for n in d.NODE_ORDER:
        hz.append(node(n, d.H[n], 44, 170, 76))
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
    horiz = f'<svg class="h" viewBox="0 18 1150 244" role="img" aria-label="Agent workflow lanes">{"".join(hz)}</svg>'

    vz = [defs]
    ys = {"Planner": 14, "Coder": 120, "Executor": 226, "Reviewer": 332, "Human": 438}
    off = 22 if fault else 0
    for n in d.NODE_ORDER:
        vz.append(node(n, 20, ys[n] + (off if n != "Planner" else 0), 230, 76))
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


def light_states() -> dict[str, dict]:
    states = copy.deepcopy(d.STATES)
    for key, s in states.items():
        nodes = s["nodes"]
        if key != "idle":  # in a live run, unreached agents are WAITING (not idle)
            for n, (status, _) in list(nodes.items()):
                if status == "idle":
                    nodes[n] = ("waiting", "AFTER REVIEW" if n == "Human" else "WAITING")
        s["body"] = re.sub(
            r'<pre class="code" style="white-space:pre-wrap;color:#ffe2a8">',
            '<pre class="code fb">',
            s["body"],
        )
        s["body"] = re.sub(
            r'<pre class="code" style="white-space:pre-wrap;color:#b9f3d3">',
            '<pre class="code okc">',
            s["body"],
        )
        s["body"] = s["body"].replace(
            '<pre class="code" style="white-space:pre-wrap">',
            '<pre class="code" style="white-space:pre-wrap">',
        )
    return states


LSTATES = light_states()

LEGEND = (
    '<div class="legend" aria-label="Node state legend"><span><i class="l-active"></i>Active</span>'
    '<span><i class="l-wait"></i>Waiting</span><span><i class="l-err"></i>Error / repair</span>'
    '<span><i class="l-fb"></i>Reviewer feedback</span><span><i class="l-ok"></i>Verified</span>'
    '<span><i class="l-hum"></i>Human pending</span></div>'
)


def livewire(key: str) -> str:
    s = LSTATES[key]
    nav = "".join(
        f'<a href="livewire-{k}.html" class="{"on" if k == key else ""}">{LSTATES[k]["label"]}</a>'
        for k in d.STATE_ORDER
    )
    rep, fbk, _, tok = s["facts"]
    kind = s["outcome"][0]
    reviewer = (
        "Approved" if key == "approved" else "Unapproved" if key == "limit-reached" else "Pending"
    )
    human = "Pending" if key == "approved" else "—"
    toolbar = (
        COMMON_TB
        + chip(s["run_chip"][0], s["run_chip"][1])
        + (chip("TEST FAULT INJECTED", "test") if s["fault"] else "")
        + f'<span class="counter" title="Real agent messages (max 12)"><span class="n num">{s["count"]}/12</span>{d.cells(s["cells"])}</span>'
    )
    feed = d.feed_html(s["feed"]) or '<div class="body muted">Waiting for the first event.</div>'
    tabs = "".join(
        f'<span class="{"on" if on else ""}">{name}</span>'
        for name, on in (
            ("Plan", s["tab"] == "Plan"),
            ("Code", s["tab"] == "Code"),
            ("Output / stderr", s["tab"] in ("Output", "Error")),
            ("Reviewer", s["tab"] == "Reviewer"),
            ("Tokens", False),
        )
    )
    body = f"""<div class="state-nav" aria-label="Mockup states (design review only)">{nav}</div>
<main class="canvas lw">
<section class="pane" aria-label="Agent workflow"><header>Agent workflow · {s["mode"]}<span class="sp"></span><span>Every motion = one real event</span></header>
{LEGEND}<div class="body">{flow_svg(s["nodes"], s["edges"], s["fault"])}</div></section>
<div class="lw-grid">
<section class="pane feed" aria-label="Message feed" aria-live="polite"><header>Live feed · runtime events</header>{feed}</section>
<section class="pane" aria-label="Inspector"><div class="tabs">{tabs}</div>{s["body"]}</section>
<aside class="pane" aria-label="Run facts"><header>Run facts</header><div class="body">
<div class="outcome {kind}" style="margin-bottom:12px"><b>{s["outcome"][1]}</b>{s["outcome"][2]}</div>
<dl class="kv">
<dt>Messages</dt><dd>{s["count"]} / 12</dd><dt>Repair attempts</dt><dd>{rep}</dd><dt>Reviewer rounds</dt><dd>{fbk}</dd>
<dt>Tokens in / out</dt><dd>{tok}</dd><dt>Cost</dt><dd>Pricing not configured</dd>
<dt>Reviewer</dt><dd>{reviewer}</dd><dt>Human</dt><dd>{human}</dd>
</dl></div></aside>
</div>
{ledger_light(key, s["count"])}</main>"""
    return shell(
        "live",
        "Agent Livewire",
        toolbar,
        body,
        f"DataPilot — Livewire: {s['label']} (light mockup)",
    )


def ledger_light(key: str, count: int) -> str:
    seq = (
        d.LEDGER_LIMIT
        if key == "limit-reached"
        else d.LEDGER_FAULT
        if key == "fault-injection"
        else d.LEDGER_FULL
    )
    rows = ""
    for i in range(min(count, len(seq))):
        a, ev, out, k = seq[i]
        mark = {
            "bad": '<span class="ic bad">✕</span>',
            "ok": '<span class="ic ok">✓</span>',
            "warn": '<span class="ic warn">!</span>',
        }.get(k, '<span class="ic"></span>')
        rows += f'<tr><td class="r num">{i + 1}</td><td>{a}</td><td class="mono">{ev}</td><td>{mark} {escape(out)}</td></tr>'
    if count < 12:
        first = count + 1
        rng = f"{first}–12" if first < 12 else "12"
        rows += (
            f'<tr class="skip"><td class="r num">{rng}</td><td colspan="3">{12 - count} of 12 messages unused'
            f"{' — no run yet' if count == 0 else ''}</td></tr>"
        )
    return (
        f'<section class="pane" aria-label="Message ledger"><header>Message ledger · {count} of 12 used'
        f'<span class="sp"></span><span>task message and events are not counted</span></header>'
        f'<div class="tscroll"><table class="t"><thead><tr><th class="r">#</th><th>Agent</th><th>Event</th><th>Outcome</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div></section>"
    )


def multi(fn, *args, w7: bool, **kw) -> str:
    """Chart variants sized to the pane at each breakpoint (CSS shows exactly one)."""
    sizes = {"cw": 1000 if w7 else 700, "cm": 700 if w7 else 480, "ct": 700, "cn": 340}
    return "".join(f'<div class="{k}">{fn(*args, **kw, w=v)}</div>' for k, v in sizes.items())


# --------------------------------------------------------------------------- Insights Studio
def insights() -> str:
    top_cat = d.top_cat
    peak = max(abs(v) for v in cat_change.values)
    rows = ""
    for c, v in cat_change.items():
        w = abs(v) / peak * 50
        bar = f'<div class="dbar"><i class="{"n" if v < 0 else "p"}" style="width:{w:.0f}%"></i></div>'
        cls = "neg" if v < 0 else "pos"
        rows += (
            f'<tr><td><b>{c}</b></td><td class="r">{m(cat.loc[c, "2026-08"])}</td><td class="r">{m(cat.loc[c, "2026-09"])}</td>'
            f'<td class="r {cls}"><b>{m(v, True)}</b></td><td class="r {cls}">{v / cat.loc[c, "2026-08"] * 100:+.1f}%</td><td>{bar}</td></tr>'
        )
    tot_aug, tot_sep = cat["2026-08"].sum(), cat["2026-09"].sum()
    rows += (
        f'<tr class="total"><td>All categories</td><td class="r">{m(tot_aug)}</td><td class="r">{m(tot_sep)}</td>'
        f'<td class="r neg">{m(tot_sep - tot_aug, True)}</td><td class="r neg">{(tot_sep / tot_aug - 1) * 100:+.1f}%</td><td></td></tr>'
    )
    toolbar = (
        COMMON_TB
        + chip("Reviewer: Approved · 9/12", "ok")
        + chip("Human: Pending", "info")
        + chip("Pricing not configured", "warn", "hide-m")
    )
    legend1 = (
        '<div class="legend"><span><i class="l-err"></i>Largest decrease</span><span><i class="l-dim"></i>Other decreases</span>'
        '<span><i class="l-active"></i>Increase</span></div>'
    )
    legend2 = '<div class="legend"><span><i class="l-err"></i>Decrease</span><span><i class="l-active"></i>Increase</span></div>'
    legend3 = '<div class="legend"><span><i class="l-err"></i>September (selected month)</span><span><i class="l-dim"></i>Other months</span></div>'
    body = f"""<div class="report">
<div class="q"><b>Question</b> · Which category had the biggest revenue drop in September vs August, and which region caused most of it?</div>
<p class="answer">{top_cat} fell the most, down <span class="neg">{m(d.TOP_DROP)}</span> from August to September, driven by <em>{d.TOP_REG}</em> ({m(d.TOP_REG_VAL)}), partly offset by growth in the other regions.</p>
<span class="chip ok"><i class="dot"></i>Reviewer approved · msg 9/12</span> <span class="chip info"><i class="dot"></i>Human approval pending</span> <span class="chip"><i class="dot"></i>12,480 rows analysed</span>
</div>
<div class="strip" aria-label="Key figures">
<div><div class="l">Sep revenue</div><div class="v num">{m(d.SEP)}</div><div class="d neg">{d.SEP_PCT:+.1f}% vs Aug</div></div>
<div><div class="l">Aug revenue</div><div class="v num">{m(d.AUG)}</div><div class="d">baseline</div></div>
<div><div class="l">Largest category drop</div><div class="v num neg">{m(d.TOP_DROP, True)}</div><div class="d">{top_cat}</div></div>
<div><div class="l">Main regional cause</div><div class="v num neg">{m(d.TOP_REG_VAL, True)}</div><div class="d">{d.TOP_REG} · within {top_cat}</div></div>
<div><div class="l">Offset elsewhere</div><div class="v num pos">{m(d.OFFSET, True)}</div><div class="d">other regions</div></div>
</div>
<main class="canvas">
<div class="vgrid">
<section class="pane chart c7" aria-label="Category change"><header>Chart 1 · Change by category<span class="sp"></span><span>Sep vs Aug</span></header>
{legend1}<div class="body">{multi(d.hbar, list(cat_change.items()), "Revenue change by category", "Revenue change (₹ million)", top_cat, w7=True)}</div></section>
<section class="pane chart c5" aria-label="Region contribution"><header>Chart 2 · {top_cat} by region<span class="sp"></span><span>drill-down</span></header>
{legend2}<div class="body">{multi(d.hbar, list(reg_change.items()), f"{top_cat}: change by region", "Revenue change (₹ million)", d.TOP_REG, w7=False)}</div></section>
<section class="pane c7" aria-label="Detail table"><header>Category detail<span class="sp"></span><span>Aug → Sep</span></header>
<div class="tscroll"><table class="t"><thead><tr><th>Category</th><th class="r">August</th><th class="r">September</th><th class="r">Change</th><th class="r">%</th><th>Contribution</th></tr></thead><tbody>{rows}</tbody></table></div></section>
<section class="pane chart c5" aria-label="Monthly revenue"><header>Chart 3 · Monthly revenue<span class="sp"></span><span>Jun–Sep</span></header>
{legend3}<div class="body">{multi(d.columns, "Revenue by month", "Revenue (₹ million)", w7=False)}</div></section>
<section class="pane narr c8" aria-label="Narrative and verification"><header>Analyst narrative<span class="sp"></span><span>AI-generated · checked by Reviewer</span></header>
<div class="body two"><div>
<p>Total revenue fell {abs(d.SEP_PCT):.1f}% from August to September. {top_cat} accounts for the largest category decline at {m(d.TOP_DROP)}.</p>
<p>Inside {top_cat}, <b>{d.TOP_REG}</b> fell {m(d.TOP_REG_VAL)}, while the other three regions together grew {m(d.OFFSET)}.</p>
<p class="src">Every figure appears in results.json or stdout. Method: revenue = units × unit_price × (1 − discount).</p></div>
<div><div class="eyebrow" style="font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:600;margin-bottom:6px">How it was verified · from the event log</div>
<div class="flag"><span class="ic bad">✕</span><span>Execution 1 failed: <span class="mono">KeyError: revenue</span> → Coder repaired from the real error</span></div>
<div class="flag"><span class="ic warn">!</span><span>Reviewer asked for axis units and an offset note → Coder revised</span></div>
<div class="flag"><span class="ic ok">✓</span><span>Execution 3 exit 0 · numbers match results.json · Reviewer APPROVED (msg 9/12)</span></div>
<div class="flag"><span class="ic info">i</span><span>analysis.py re-run twice → identical results hash</span></div></div></div></section>
<section class="pane c4" aria-label="Verification and exports"><header>Verification &amp; exports</header><div class="body">
<div class="verify">
<div class="row"><span class="muted">Reviewer</span><span class="chip ok"><i class="dot"></i>Approved · msg 9</span></div>
<div class="row"><span class="muted">Execution</span><span>2 errors repaired · exit 0</span></div>
<div class="row"><span class="muted">Human</span><span class="chip info"><i class="dot"></i>Pending</span></div>
</div>
<div class="dl" style="margin-top:12px"><span class="btn">↓ analysis.py</span><span class="btn">↓ PNG · 2 charts</span><span class="btn">↓ PDF · 1 page</span></div>
</div></section>
</div>
<section class="pane" aria-label="Decision and follow-up">
<div class="approval"><b>Your decision</b><span class="muted">Reviewer approval does not finalize the report.</span><span class="sp"></span>
<span class="btn danger">Reject</span><span class="btn ok">Approve report</span></div>
<div class="followup"><div class="in">Ask a follow-up in this session, e.g. “Which South products fell most?”</div><span class="btn primary">Ask follow-up</span></div>
<div class="followup" style="border-top:0;padding-top:0"><span class="nt">A follow-up starts a new run with a fresh 12-message budget and keeps this dataset and history.</span></div></section>
</main>"""
    return shell(
        "ins", "Insights Studio", toolbar, body, "DataPilot — Insights Studio (light mockup)"
    )


# --------------------------------------------------------------------------- tokens
TOKENS = [
    ("--canvas", "#f7f6f2", "Warm ivory · page canvas"),
    ("--surface", "#ffffff", "Primary surfaces"),
    ("--surface-2", "#e9edf0", "Secondary surfaces"),
    ("--ink", "#233247", "Primary text (slate)"),
    ("--muted", "#566679", "Secondary text"),
    ("--accent", "#077a86", "Deep teal · action (user #087F8C, AA-nudged)"),
    ("--gold", "#b58429", "Restrained gold · feedback (user #C49545 → --gold-soft)"),
    ("--ok", "#1f7f63", "Verified / success"),
    ("--danger", "#c7515c", "Error / unapproved (coral)"),
    ("--info", "#3a6ea5", "Human stage / info"),
    ("--neutral-bar", "#8795a5", "Neutral chart bars"),
    ("--line", "#dde2e7", "Hairlines"),
]
TEXT_PAIRS = [
    ("--ink", "#233247", "--surface", "#ffffff", 4.5),
    ("--ink", "#233247", "--canvas", "#f7f6f2", 4.5),
    ("--ink", "#233247", "--surface-2", "#e9edf0", 4.5),
    ("--muted", "#566679", "--surface", "#ffffff", 4.5),
    ("--muted", "#566679", "--canvas", "#f7f6f2", 4.5),
    ("--muted", "#566679", "--surface-2", "#e9edf0", 4.5),
    ("--muted", "#566679", "--surface-3 (#f1f3f5)", "#f1f3f5", 4.5),
    ("white on --accent (buttons)", "#ffffff", "--accent", "#077a86", 4.5),
    ("--accent (links)", "#077a86", "--surface", "#ffffff", 4.5),
    ("teal text #065a63", "#065a63", "--accent-tint #e2f1f2", "#e2f1f2", 4.5),
    ("--ok-ink #1a6b55", "#1a6b55", "--ok-tint #e4f2ed", "#e4f2ed", 4.5),
    ("--danger-ink #a8323f", "#a8323f", "--danger-tint #fbebed", "#fbebed", 4.5),
    ("--danger-ink #a8323f", "#a8323f", "--surface", "#ffffff", 4.5),
    ("--gold-ink #7d5a12", "#7d5a12", "--gold-tint #fbf3e0", "#fbf3e0", 4.5),
    ("info text #25507c", "#25507c", "--info-tint #e8eff7", "#e8eff7", 4.5),
]
GRAPHIC_PAIRS = [
    ("--accent (bars, active edge)", "#077a86", "--surface", "#ffffff", 3.0),
    ("--danger (error bars, repair edge)", "#c7515c", "--surface", "#ffffff", 3.0),
    ("--gold (feedback edge, badges)", "#b58429", "--surface", "#ffffff", 3.0),
    ("--ok (verified)", "#1f7f63", "--surface", "#ffffff", 3.0),
    ("--neutral-bar", "#8795a5", "--surface", "#ffffff", 3.0),
    ("--info (human pending)", "#3a6ea5", "--surface", "#ffffff", 3.0),
]


def tokens_page() -> str:
    sw = "".join(
        f'<div><i style="background:{h}"></i><span><b>{n}</b><br><span class="num">{h}</span><br><span class="muted">{desc}</span></span></div>'
        for n, h, desc in TOKENS
    )

    def table(pairs: list) -> str:
        out = ""
        for fn, fh, bn, bh, need in pairs:
            r = d.ratio(fh, bh)
            ok = "<span class=pos>PASS</span>" if r >= need else "<span class=neg>FAIL</span>"
            out += f'<tr><td>{fn}</td><td>{bn}</td><td class="r num">{r:.2f}:1</td><td class="r">{need:g}:1</td><td>{ok}</td></tr>'
        return out

    head = "<thead><tr><th>Foreground</th><th>Background</th><th class=r>Ratio</th><th class=r>Needed</th><th>Result</th></tr></thead>"

    def lite(t: str) -> str:
        for a, b in (
            ("Amber", "Gold"),
            ("red feed row", "coral feed row"),
            ("Animated red edge", "Animated coral edge"),
            ("cell turns red", "cell turns coral"),
        ):
            t = t.replace(a, b)
        return t

    mp = "".join(
        f"<tr><td>{a}</td><td class='mono'>{b}</td><td>{lite(c)}</td></tr>" for a, b, c in d.MAP
    )
    states = "".join(
        f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>"
        for a, b, c in [
            (
                "Active",
                "Teal tint, 2 px teal border, left bar, pulse (event only)",
                "▶ ACTIVE / WRITING / REPAIRING",
            ),
            ("Waiting", "Dashed grey border, muted text", "⋯ WAITING / AFTER REVIEW"),
            (
                "Error / repair",
                "Coral tint, coral border; coral dashed repair edge Executor → Coder",
                "✕ ERROR · EXIT 1",
            ),
            (
                "Reviewer feedback",
                "Gold tint; gold dashed feedback edge Reviewer → Coder",
                "! FEEDBACK · n ISSUES",
            ),
            ("Reviewer approved", "Green tint, 2.4 px green border", "✓ APPROVED · MSG n"),
            (
                "Human pending",
                "Blue-grey tint, dashed blue border; separate node",
                "◌ PENDING DECISION",
            ),
            (
                "Unapproved / limit",
                "Coral terminal on Human node + toolbar chip",
                "✕ RUN UNAPPROVED",
            ),
            ("Test fault", "Gold badge over the Coder node + toolbar chip", "TEST FAULT INJECTED"),
        ]
    )
    body = f"""<main class="canvas">
<section class="pane"><header>Colour tokens</header><div class="body"><div class="sw">{sw}</div></div></section>
<section class="pane"><header>Text contrast (WCAG 2.1 AA, computed)</header><div class="tscroll"><table class="t">{head}<tbody>{table(TEXT_PAIRS)}</tbody></table></div></section>
<section class="pane"><header>Graphics contrast (non-text, 3:1)</header><div class="tscroll"><table class="t">{head}<tbody>{table(GRAPHIC_PAIRS)}</tbody></table></div></section>
<section class="pane"><header>Agent state language (light)</header><div class="tscroll"><table class="t"><thead><tr><th>State</th><th>Treatment</th><th>Label (never colour alone)</th></tr></thead><tbody>{states}</tbody></table></div></section>
<section class="pane"><header>Type, space, shape</header><div class="body"><dl class="kv" style="grid-template-columns:150px 1fr">
<dt>Sans</dt><dd style="text-align:left">Segoe UI / system UI — UI, tables, labels</dd>
<dt>Serif</dt><dd style="text-align:left">Georgia — the answer headline, narrative and composer (report voice)</dd>
<dt>Mono</dt><dd style="text-align:left">Cascadia Mono / Consolas — code, stderr, event names</dd>
<dt>Scale</dt><dd style="text-align:left">11 · 12 · 13 (body) · 15 · 24–26 (answer) · 28 (KPI, tabular numerals)</dd>
<dt>Shape</dt><dd style="text-align:left">3 px radius, 1 px hairlines, no shadows, no card grid</dd>
<dt>Motion</dt><dd style="text-align:left">Edge flow / node pulse only on real events; off under prefers-reduced-motion</dd>
<dt>Breakpoints</dt><dd style="text-align:left">≥1400 · 1024–1399 · 768–1023 (vertical lanes) · &lt;768 (bottom tabs)</dd></dl></div></section>
<section class="pane"><header>Livewire state → RuntimeEvent mapping</header><div class="tscroll"><table class="t"><thead><tr><th>Visual state</th><th>Real source event(s)</th><th>What the UI shows</th></tr></thead><tbody>{mp}</tbody></table></div></section>
</main>"""
    return shell(
        "ask", "Design tokens", COMMON_TB, body, "DataPilot — Design tokens (light mockup)"
    )


def main() -> None:
    PAGES.mkdir(exist_ok=True)
    pages = {"ask-explore": ask_explore(), "insights-studio": insights(), "tokens": tokens_page()}
    pages |= {f"livewire-{k}": livewire(k) for k in d.STATE_ORDER}
    for name, html in pages.items():
        (PAGES / f"{name}.html").write_text(html, encoding="utf-8")
    sys.stdout.write(f"built {len(pages)} light pages\n")


if __name__ == "__main__":
    main()

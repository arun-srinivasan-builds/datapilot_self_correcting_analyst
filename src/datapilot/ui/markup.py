"""HTML fragments for the approved light UI. Every dynamic string is escaped (data is untrusted)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from html import escape

from datapilot.ui.viewmodel import NODE_ORDER, NODE_SUB, Canvas, FeedItem, LedgerRow

# Streamlit's markdown pass collapses raw newlines inside HTML blocks; a numeric reference survives it.
NL = "&#10;"

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


def chip(text: str, kind: str = "", cls: str = "") -> str:
    return f'<span class="chip {kind} {cls}"><i class="dot"></i>{escape(text)}</span>'


def toolbar(crumb: str, chips: Iterable[str]) -> str:
    return (
        f'<div class="dp-toolbar"><div class="crumb">DataPilot <span>/ {escape(crumb)}</span></div>'
        f'<div class="sp" style="flex:1"></div>{"".join(chips)}</div>'
    )


def banner(text: str) -> str:
    return f'<div class="dp-banner"><b>DESIGN PREVIEW</b><span>{escape(text)}</span></div>'


def pane_header(title: str, right: str = "", step: int | None = None) -> str:
    s = f'<span class="step">{step}</span>' if step else ""
    r = f"<span>{escape(right)}</span>" if right else ""
    return f'<div class="ph">{s}{escape(title)}<span class="sp"></span>{r}</div>'


def pane(title: str, body: str, right: str = "", label: str | None = None) -> str:
    aria = escape(label or title)
    return (
        f'<section class="dp-pane" aria-label="{aria}">{pane_header(title, right)}{body}</section>'
    )


def strip(items: Sequence[tuple[str, str, str]]) -> str:
    """(label, value_html, sub_html) KPI strip; value/sub are pre-escaped HTML supplied by callers."""
    cells = "".join(
        f'<div><div class="l">{escape(label)}</div><div class="v num">{value}</div><div class="d">{sub}</div></div>'
        for label, value, sub in items
    )
    return f'<div class="strip" aria-label="Key figures">{cells}</div>'


def table(headers: Sequence[str], rows: Sequence[Sequence[str]], right: Iterable[int] = ()) -> str:
    """Rows contain pre-escaped HTML cells."""
    r = set(right)
    head = "".join(
        f'<th class="{"r" if i in r else ""}">{escape(h)}</th>' for i, h in enumerate(headers)
    )
    body = "".join(
        "<tr>"
        + "".join(f'<td class="{"r" if i in r else ""}">{c}</td>' for i, c in enumerate(row))
        + "</tr>"
        for row in rows
    )
    return f'<div class="tscroll"><table class="t"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


# --------------------------------------------------------------------------- Livewire
def counter(count: int, tones: Sequence[str]) -> str:
    cls = {"bad": "err", "ok": "ok", "warn": "warn", "": "on"}
    cells = [cls.get(t, "on") for t in tones[:12]] + [""] * (12 - len(tones[:12]))
    boxes = "".join(f'<i class="{c}"></i>' for c in cells)
    return (
        f'<span class="counter" title="Real agent messages (max 12)"><span class="n num">{count}/12</span>'
        f'<span class="cells" aria-hidden="true">{boxes}</span></span>'
    )


LEGEND = (
    '<div class="legend" aria-label="Node state legend"><span><i class="l-active"></i>Active</span>'
    '<span><i class="l-wait"></i>Waiting</span><span><i class="l-err"></i>Error / repair</span>'
    '<span><i class="l-fb"></i>Reviewer feedback</span><span><i class="l-ok"></i>Verified</span>'
    '<span><i class="l-hum"></i>Human pending</span></div>'
)

_HX = {"Planner": 20, "Coder": 250, "Executor": 480, "Reviewer": 710, "Human": 960}
_VY = {"Planner": 14, "Coder": 120, "Executor": 226, "Reviewer": 332, "Human": 438}


def flow_svg(canvas: Canvas) -> str:
    """Horizontal + vertical lanes (CSS swaps them below 1024px). Rendered from the event-derived view."""
    labels: list[str] = []
    fault = canvas.fault

    def node(name: str, x: int, y: int, w: int, h: int) -> str:
        view = canvas.nodes[name]
        badge = ""
        if name == "Coder" and fault:
            badge = (
                f'<g class="badge-fault"><rect x="{x}" y="{y - 22}" width="{w}" height="18" rx="2"/>'
                f'<text x="{x + w / 2}" y="{y - 9}" text-anchor="middle">TEST FAULT INJECTED</text></g>'
            )
        return (
            f'<g class="node is-{view.status}"><rect class="body" x="{x}" y="{y}" width="{w}" height="{h}" rx="3"/>'
            f'<rect class="sbar" x="{x}" y="{y}" width="5" height="{h}" rx="1"/>'
            f'<text x="{x + 16}" y="{y + 26}">{name}</text>'
            f'<text class="sub" x="{x + 16}" y="{y + 44}">{escape(NODE_SUB[name])}</text>'
            f'<text class="st" x="{x + 16}" y="{y + h - 10}">{GLYPH.get(view.status, "")}{escape(view.label)}</text>'
            f"{badge}</g>"
        )

    def edge(
        name: str,
        path: str,
        label: str = "",
        lx: int = 0,
        ly: int = 0,
        kind: str = "",
        rot: bool = False,
    ) -> str:
        cls = canvas.edges.get(name, "")
        if label and cls:
            tf = f' transform="rotate(-90 {lx} {ly})"' if rot else ""
            labels.append(
                f'<text class="elabel {kind}" x="{lx}" y="{ly}" text-anchor="middle"{tf}>{label}</text>'
            )
        return f'<path class="edge {cls}" d="{path}" marker-end="url(#a)"/>'

    defs = (
        '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        'orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#6b7a8c"/></marker></defs>'
    )
    hz = [defs, *(node(n, _HX[n], 44, 170, 76) for n in NODE_ORDER)]
    hz += [
        edge("p_c", "M190 82H248"),
        edge("c_e", "M420 82H478"),
        edge("e_r", "M650 82H708"),
        edge("r_h", "M880 82H958"),
        edge(
            "repair",
            "M565 120C565 168 372 168 372 122",
            "REPAIR · error returned to Coder",
            468,
            176,
            "repair",
        ),
        edge(
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
    off = 22 if fault else 0
    vz = [defs]
    for n in NODE_ORDER:
        vz.append(node(n, 20, _VY[n] + (off if n != "Planner" else 0), 230, 76))
    vz += [
        edge("p_c", f"M135 90V{118 + off}"),
        edge("c_e", f"M135 {196 + off}V{224 + off}"),
        edge("e_r", f"M135 {302 + off}V{330 + off}"),
        edge("r_h", f"M135 {408 + off}V{436 + off}"),
        edge(
            "repair",
            f"M250 {264 + off}C302 {264 + off} 302 {158 + off} 252 {158 + off}",
            "REPAIR",
            273,
            211 + off,
            "repair",
            True,
        ),
        edge(
            "feedback",
            f"M250 {370 + off}C372 {370 + off} 372 {170 + off} 252 {170 + off}",
            "FEEDBACK",
            322,
            270 + off,
            "feedback",
            True,
        ),
    ]
    vz += labels
    vert = f'<svg class="v" viewBox="0 0 380 {540 + off}" role="img" aria-label="Agent workflow lanes">{"".join(vz)}</svg>'
    return f'<div class="lanes" style="padding:var(--pad)">{horiz}{vert}</div>'


def feed_html(items: Sequence[FeedItem]) -> str:
    if not items:
        return '<div class="dp-empty" style="padding:var(--pad)">Waiting for the first real event.</div>'
    return "".join(
        f'<div class="feed"><div class="m {escape(i.cls)}"><span class="s">{escape(i.marker)}</span>'
        f'<div><span class="who">{escape(i.who)}</span> <span class="muted">{escape(i.text)}</span></div></div></div>'
        for i in items
    )


_NOMARK = '<span class="ic"></span>'
_MARK = {
    "bad": '<span class="ic bad">✕</span>',
    "ok": '<span class="ic ok">✓</span>',
    "warn": '<span class="ic warn">!</span>',
}


def ledger_html(rows: Sequence[LedgerRow]) -> str:
    n = len(rows)
    body = "".join(
        f'<tr><td class="r num">{r.index}</td><td>{escape(r.agent)}</td><td class="mono">{escape(r.event)}</td>'
        f"<td>{_MARK.get(r.tone, _NOMARK)} {escape(r.outcome)}</td></tr>"
        for r in rows
    )
    if n < 12:
        rng = f"{n + 1}–12" if n + 1 < 12 else "12"
        note = " — no run yet" if n == 0 else ""
        body += f'<tr class="skip"><td class="r num">{rng}</td><td colspan="3">{12 - n} of 12 messages unused{note}</td></tr>'
    head = '<tr><th class="r">#</th><th>Agent</th><th>Event</th><th>Outcome</th></tr>'
    title = f"Message ledger · {n} of 12 used"
    return (
        f'<section class="dp-pane" aria-label="Message ledger">'
        f"{pane_header(title, 'task message and events are not counted')}"
        f'<div class="tscroll"><table class="t"><thead>{head}</thead><tbody>{body}</tbody></table></div></section>'
    )


_KW = re.compile(r"\b(import|from|as|def|return|for|in|if|else|None|True|False)\b")


def highlight(code: str, mark_line: int = 0, mark_kind: str = "") -> str:
    """Tiny, safe syntax highlighter: escape first, then wrap comments/strings/keywords."""
    out = []
    for i, raw in enumerate(code.splitlines(), 1):
        line = escape(raw)
        if raw.lstrip().startswith("#"):
            line = f'<span class="c">{line}</span>'
        else:
            line = re.sub(r"(&quot;.*?&quot;|&#x27;.*?&#x27;)", r'<span class="s">\1</span>', line)
            line = _KW.sub(r'<span class="k">\1</span>', line)
        if i == mark_line and mark_kind in ("hl", "add", "del"):
            line = f'<span class="{mark_kind}">{line}</span>'
        out.append(line)
    return NL.join(out)


def code_block(code: str, mark_line: int = 0, mark_kind: str = "") -> str:
    return f'<div class="codeblock">{highlight(code, mark_line, mark_kind)}</div>'


def err_block(text: str) -> str:
    return f'<div class="errblock">{escape(text).replace(chr(10), NL)}</div>'


def text_block(text: str, cls: str = "") -> str:
    return f'<div class="codeblock {cls}">{escape(text).replace(chr(10), NL)}</div>'


def facts_html(canvas: Canvas, reviewer: str, human: str, tokens: str) -> str:
    s = canvas.state
    return (
        '<dl class="kv" style="padding:var(--pad)">'
        f"<dt>Messages</dt><dd>{s.message_count} / 12</dd>"
        f"<dt>Repair attempts</dt><dd>{s.repair_attempts}</dd>"
        f"<dt>Reviewer rounds</dt><dd>{s.feedback_rounds}</dd>"
        f"<dt>Tokens in / out</dt><dd>{escape(tokens)}</dd>"
        f"<dt>Reviewer</dt><dd>{escape(reviewer)}</dd><dt>Human</dt><dd>{escape(human)}</dd></dl>"
    )


def outcome_html(kind: str, title: str, body: str) -> str:
    return f'<div class="outcome {kind}" style="margin:var(--pad) var(--pad) 0"><b>{escape(title)}</b>{escape(body)}</div>'

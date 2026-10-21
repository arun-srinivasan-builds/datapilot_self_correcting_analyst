"""Static SVG charts matching the approved light mockups. Data in, markup out; all text escaped."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from html import escape

MINUS = "−"


def money_m(value: float, signed: bool = False) -> str:
    text = f"{abs(value) / 1e6:,.2f}"
    if signed:
        return ("+" if value >= 0 else MINUS) + "₹" + text + "M"
    return "₹" + text + "M"


Formatter = Callable[[float, bool], str]


def hbar(
    items: Sequence[tuple[str, float]],
    title: str,
    xlabel: str,
    highlight: str | None,
    w: int = 1000,
    fmt: Formatter = money_m,
) -> str:
    """Diverging horizontal bars with guaranteed label room on both sides."""
    narrow = w <= 500
    rowh, left, right, top, room = (34, 66, 4, 40, 54) if narrow else (34, 96, 16, 40, 78)
    h = top + rowh * len(items) + 44
    neg = max([-v for _, v in items if v < 0] or [0.0])
    pos = max([v for _, v in items if v > 0] or [0.0])
    span = (neg + pos) or 1.0
    scale = (w - left - right - 2 * room) / span
    zero = left + room + neg * scale
    lo, hi = zero - neg * scale - room, zero + pos * scale + room
    out = [f'<text class="t" x="0" y="16">{escape(title)}</text>']
    step = (2e6 if span > 5e6 else 0.5e6) * (2 if narrow else 1)
    tick = -(neg // step) * step - (step if neg % step else 0)
    while tick <= pos + step:
        x = zero + tick * scale
        if lo <= x <= hi:
            out.append(
                f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{top - 8}" y2="{h - 36}"/>'
                f'<text x="{x:.1f}" y="{h - 20}" text-anchor="middle">{tick / 1e6:+.1f}</text>'
            )
        tick += step
    for i, (name, value) in enumerate(items):
        y = top + i * rowh
        width = abs(value) * scale
        x = zero if value >= 0 else zero - width
        cls = "posb" if value >= 0 else ("neg" if name == highlight else "dim")
        ax = (x + width + 6) if value >= 0 else (x - 6)
        anchor = "start" if value >= 0 else "end"
        out.append(
            f'<text x="{left - 8}" y="{y + 19}" text-anchor="end">{escape(name)}</text>'
            f'<rect class="{cls}" x="{x:.1f}" y="{y + 4}" width="{width:.1f}" height="20" rx="1"/>'
            f'<text class="ann" x="{ax:.1f}" y="{y + 19}" text-anchor="{anchor}">'
            f"{escape(fmt(value, True))}</text>"
        )
    out.append(
        f'<line class="axis" x1="{zero:.1f}" x2="{zero:.1f}" y1="{top - 8}" y2="{h - 36}"/>'
        f'<text x="{(lo + hi) / 2:.0f}" y="{h - 4}" text-anchor="middle">{escape(xlabel)}</text>'
    )
    return (
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">{"".join(out)}</svg>'
    )


def columns(
    items: Sequence[tuple[str, float]],
    title: str,
    ylabel: str,
    highlight: str | None,
    w: int = 1000,
) -> str:
    """Vertical columns (e.g. monthly totals) with a highlighted period."""
    narrow = w <= 500
    h, left, bottom, top = 260, 56, 40, 40
    peak = max((v for _, v in items), default=1.0) or 1.0
    unit = next(
        (u for u in (1e6, 2e6, 5e6, 10e6, 20e6, 25e6, 50e6, 100e6) if peak * 1.1 / u <= 4), 100e6
    )
    ymax = unit * (int(peak * 1.1 / unit) + 1)
    bw = 48 if narrow else 110
    out = [f'<text class="t" x="0" y="16">{escape(title)}</text>']
    for k in range(int(ymax / unit) + 1):
        v = unit * k
        y = h - bottom - (h - bottom - top) * v / ymax
        out.append(
            f'<line class="grid" x1="{left}" x2="{w - 10}" y1="{y:.1f}" y2="{y:.1f}"/>'
            f'<text x="{left - 6}" y="{y + 4:.1f}" text-anchor="end">{v / 1e6:.0f}</text>'
        )
    step = (w - left - 10) / max(len(items), 1)
    for i, (label, value) in enumerate(items):
        bh = (h - bottom - top) * value / ymax
        x = left + i * step + (step - bw) / 2
        cls = "neg" if label == highlight else "dim"
        shown = label[-2:] if narrow and len(label) > 4 else label
        out.append(
            f'<rect class="{cls}" x="{x:.1f}" y="{h - bottom - bh:.1f}" width="{bw}" height="{bh:.1f}" rx="1"/>'
            f'<text class="ann" x="{x + bw / 2:.1f}" y="{h - bottom - bh - 6:.1f}" text-anchor="middle">{value / 1e6:.1f}</text>'
            f'<text x="{x + bw / 2:.1f}" y="{h - bottom + 16}" text-anchor="middle">{escape(shown)}</text>'
        )
    mid = (top + h - bottom) / 2
    out.append(
        f'<line class="axis" x1="{left}" x2="{w - 10}" y1="{h - bottom}" y2="{h - bottom}"/>'
        f'<text x="12" y="{mid:.0f}" transform="rotate(-90 12 {mid:.0f})" text-anchor="middle">{escape(ylabel)}</text>'
    )
    return (
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">{"".join(out)}</svg>'
    )


def variants(fn: Callable[..., str], *args: object, wide: int, mid: int, **kw: object) -> str:
    """Chart sized for each breakpoint (CSS shows exactly one): wide, laptop, tablet, mobile."""
    sizes = {"cw": wide, "cm": mid, "ct": 700, "cn": 340}
    return "".join(f'<div class="{k}">{fn(*args, w=v, **kw)}</div>' for k, v in sizes.items())

"""Assemble the visual review package (HTML + PDF) from review/png and review/checks.json.

.venv\\Scripts\\python docs/mockups/review/capture_review.py   # screenshots + automated checks
.venv\\Scripts\\python docs/mockups/review/build_review.py     # HTML + PDF
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from html import escape
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PNG = HERE / "png"
sys.path.insert(0, str(HERE))
from capture_light import SCREENS, VIEWPORTS  # noqa: E402

CHECKS = json.loads((HERE / "checks.json").read_text(encoding="utf-8"))
VP_LABEL = {
    "desktop-1920": "Desktop 1920",
    "laptop-1366": "Laptop 1366",
    "tablet-820": "Tablet 820",
    "mobile-390": "Mobile 390",
}
SCALE = 2  # screenshots were captured at device scale factor 2

NOTES = {
    "ask-explore": "Profile strip first, then source / preview / composer panes. On mobile the composer is promoted above the preview.",
    "insights-studio": "Answer first, KPI strip, three coordinated charts (narrow chart variants below 768 px), narrative with verification trail, exports, separate decision bar.",
    "tokens": "Palette tokens, computed WCAG contrast, type/space/shape rules and the state to RuntimeEvent mapping.",
}
for _s in (
    "idle",
    "running",
    "exec-error",
    "repair",
    "reviewer-feedback",
    "approved",
    "limit-reached",
    "fault-injection",
):
    NOTES[f"livewire-{_s}"] = {
        "idle": "Armed canvas, 0/12, empty feed. Nothing animates without a real event.",
        "running": "Planner done (message 1), Coder active. Counter equals real messages only.",
        "exec-error": "Executor error state with the real stderr in the inspector; cell turns red.",
        "repair": "Red edge Executor to Coder: the real error is returned to the Coder (attempt 1).",
        "reviewer-feedback": "Amber edge Reviewer to Coder; feedback text in the inspector; Executor shows OK.",
        "approved": "Reviewer APPROVED on message 9. The Human node is a separate dashed PENDING stage.",
        "limit-reached": "12/12 used without approval: terminal 'Unapproved' state, never styled as verified.",
        "fault-injection": "Persistent TEST FAULT INJECTED badge (toolbar + Coder node); never styled as a natural error.",
    }[_s]


def img(stem: str, vp: str) -> Path:
    return PNG / f"{stem}__{vp}.png"


def verdict(stem: str) -> tuple[bool, dict[str, dict]]:
    per = CHECKS[stem]
    ok = all(
        r["overflowX"] <= 0
        and not (r["clipped"] or r["overlaps"] or r["contrast"] or r["offscreen"])
        for r in per.values()
    )
    return ok, per


OK_MARK, BAD_MARK, MID_DOT = "●", "▲", "·"
ALL_OK = all(verdict(s)[0] for s, _ in SCREENS)

# ----------------------------------------------------------------------------- HTML review
CSS = """
:root{--bg:#f7f6f2;--surface:#ffffff;--surface-2:#e9edf0;--line:#dde2e7;--accent:#077a86;--text:#233247;--muted:#566679;--ok:#1a6b55;--warn:#7d5a12;--danger:#a8323f}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 "Segoe UI",system-ui,sans-serif;display:grid;grid-template-columns:260px minmax(0,1fr)}
a{color:var(--accent);text-decoration:none}
nav.toc{position:sticky;top:0;height:100vh;overflow:auto;background:var(--surface);border-right:1px solid var(--line);padding:16px 14px}
nav.toc h1{font:700 17px Georgia,serif;margin:0 0 4px}nav.toc .sub{color:var(--muted);font-size:12px;margin-bottom:14px}
nav.toc h2{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:16px 0 6px}
nav.toc a{display:flex;justify-content:space-between;gap:8px;padding:5px 8px;border-radius:3px;color:var(--text);font-size:13px}
nav.toc a:hover,nav.toc a:focus-visible{background:var(--surface-2)}
.dot{font-size:11px}.dot.ok{color:var(--ok)}.dot.bad{color:var(--danger)}
main{padding:24px 28px;min-width:0}
section.screen{margin:0 0 44px;padding-top:8px;border-top:1px solid var(--line)}
section.screen h2{font:700 21px Georgia,serif;margin:12px 0 2px}
.note{color:var(--muted);margin:0 0 12px;max-width:80ch}
.panel{display:none}
input.r{position:absolute;opacity:0;pointer-events:none}
input.r:focus-visible + label{outline:2px solid var(--accent);outline-offset:2px}
.tabset label{display:inline-block;margin:0 6px 10px 0;border:1px solid var(--line);border-radius:3px;padding:5px 12px;cursor:pointer;background:var(--surface);font-size:13px}
.frame{background:var(--surface);border:1px solid var(--line);border-radius:3px;padding:10px;overflow:auto}
.frame img{display:block;max-width:100%;height:auto;border:1px solid var(--line);margin:0 auto}
.frame.mobile img{max-width:390px}.frame.tablet img{max-width:820px}
.meta{color:var(--muted);font-size:12px;margin-top:6px}
.pill{display:inline-block;border:1px solid var(--line);border-radius:3px;padding:1px 8px;font-size:12px}
.pill.ok{border-color:#9fcfbf;color:var(--ok);background:#e4f2ed}.pill.bad{border-color:#e3a9af;color:var(--danger);background:#fbebed}
table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0;background:var(--surface)}
th,td{border-bottom:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600;background:#f1f3f5}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:3px;padding:12px 14px}
.card h3{margin:0 0 6px;font-size:14px}
.card ul{margin:0;padding-left:18px}
.sw{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}.sw span{border:1px solid var(--line);border-radius:3px;padding:6px 10px;font-size:12px}
.pager{display:flex;justify-content:space-between;margin-top:10px;font-size:13px}
@media(max-width:900px){body{grid-template-columns:1fr}nav.toc{position:static;height:auto}}
"""


def tabs_html(stem: str, label: str) -> str:
    out = [f'<div class="tabset" role="tablist" aria-label="Viewport for {escape(label)}">']
    for i, vp in enumerate(VIEWPORTS):
        out.append(
            f'<input class="r" type="radio" name="vp-{stem}" id="{stem}-{vp}"{" checked" if i == 0 else ""}>'
            f'<label for="{stem}-{vp}" role="tab">{VP_LABEL[vp]}</label>'
        )
    panels = []
    for vp, (w, _) in VIEWPORTS.items():
        kind = "mobile" if w < 500 else "tablet" if w < 1000 else ""
        r = CHECKS[stem][vp]
        status = (
            '<span class="pill ok">checks passed</span>'
            if r["overflowX"] <= 0
            and not (r["clipped"] or r["overlaps"] or r["contrast"] or r["offscreen"])
            else '<span class="pill bad">findings</span>'
        )
        panels.append(
            f'<div class="panel" data-vp="{vp}"><div class="frame {kind}">'
            f'<a href="png/{stem}__{vp}.png" target="_blank" rel="noopener"><img src="png/{stem}__{vp}.png" loading="lazy" '
            f'alt="{escape(label)} at {w}px"></a></div>'
            f'<div class="meta">{VP_LABEL[vp]} · page height {r["pageHeight"]}px {status} · '
            f'<a href="png/{stem}__{vp}.png" target="_blank" rel="noopener">open full size</a></div></div>'
        )
    return "".join(out) + "".join(panels) + "</div>"


def tab_css() -> str:
    rules = []
    for stem, _ in SCREENS:
        for vp in VIEWPORTS:
            rules.append(f'#{stem}-{vp}:checked ~ .panel[data-vp="{vp}"]{{display:block}}')
            rules.append(
                f"#{stem}-{vp}:checked + label{{border-color:var(--accent);background:var(--surface-2)}}"
            )
    return "\n".join(rules)


def build_html() -> str:
    toc = [
        '<h2>Overview</h2><a href="#summary">Summary &amp; findings</a><a href="#checks">Viewport checks</a>'
        '<a href="#tokens-notes">Tokens &amp; consistency</a><h2>Screens</h2>'
    ]
    for stem, label in SCREENS:
        if stem.startswith("livewire") or stem == "tokens":
            continue
        ok = verdict(stem)[0]
        toc.append(
            f'<a href="#{stem}">{escape(label)}<span class="dot {"ok" if ok else "bad"}">{OK_MARK if ok else BAD_MARK}</span></a>'
        )
    toc.append("<h2>Agent Livewire states</h2>")
    for stem, label in SCREENS:
        if stem.startswith("livewire"):
            ok = verdict(stem)[0]
            toc.append(
                f'<a href="#{stem}">{escape(label.split(MID_DOT)[1].strip().capitalize())}'
                f'<span class="dot {"ok" if ok else "bad"}">{OK_MARK if ok else BAD_MARK}</span></a>'
            )
    toc.append(
        '<h2>Reference</h2><a href="#tokens">Design tokens page</a><a href="gallery.html">Screenshot gallery</a><a href="pages/ask-explore.html">Live pages</a><a href="../review/DataPilot_UI_Review.html">Original dark review</a>'
    )

    matrix = [
        "<table><thead><tr><th>Screen</th>"
        + "".join(f"<th>{VP_LABEL[v]}</th>" for v in VIEWPORTS)
        + "</tr></thead><tbody>"
    ]
    for stem, label in SCREENS:
        cells = []
        for vp in VIEWPORTS:
            r = CHECKS[stem][vp]
            bad = (
                r["overflowX"] > 0
                or r["clipped"]
                or r["overlaps"]
                or r["contrast"]
                or r["offscreen"]
            )
            cells.append(
                f'<td><span class="pill {"bad" if bad else "ok"}">{"findings" if bad else "pass"}</span></td>'
            )
        matrix.append(f"<tr><td>{escape(label)}</td>{''.join(cells)}</tr>")
    matrix.append("</tbody></table>")

    secs = []
    order = [s for s in SCREENS if s[0] != "tokens"] + [s for s in SCREENS if s[0] == "tokens"]
    for idx, (stem, label) in enumerate(order):
        prev_a = (
            f'<a href="#{order[idx - 1][0]}">← {escape(order[idx - 1][1])}</a>'
            if idx
            else "<span></span>"
        )
        next_a = (
            f'<a href="#{order[idx + 1][0]}">{escape(order[idx + 1][1])} →</a>'
            if idx < len(order) - 1
            else "<span></span>"
        )
        secs.append(
            f'<section class="screen" id="{stem}"><h2>{escape(label)}</h2><p class="note">{escape(NOTES[stem])}</p>'
            f'{tabs_html(stem, label)}<div class="pager">{prev_a}{next_a}</div></section>'
        )

    from_tokens = [
        ("--canvas", "#f7f6f2", "ivory canvas"),
        ("--surface", "#ffffff", "surface"),
        ("--surface-2", "#e9edf0", "secondary"),
        ("--ink", "#233247", "slate text"),
        ("--accent", "#077a86", "deep teal"),
        ("--gold", "#b58429", "gold"),
        ("--ok", "#1f7f63", "verified"),
        ("--danger", "#c7515c", "coral error"),
        ("--info", "#3a6ea5", "human stage"),
    ]
    dark_fill = ("--ink", "--accent", "--ok", "--danger", "--info", "--gold")
    sw = "".join(
        f'<span style="background:{h};color:{"#ffffff" if n in dark_fill else "#233247"}">{n} {h} {MID_DOT} {desc}</span>'
        for n, h, desc in from_tokens
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DataPilot UI Review (Light)</title><style>{CSS}{tab_css()}</style></head><body>
<nav class="toc" aria-label="Review navigation"><h1>DataPilot UI Review · Light</h1><div class="sub">M2 mockups · {date.today().isoformat()}<br>Design only — no Streamlit code yet</div>{"".join(toc)}</nav>
<main>
<section id="summary"><h1 style="margin:0 0 4px">Visual review package</h1>
<p class="note">Premium LIGHT theme mockups of the three workspaces and eight Agent Livewire states at four viewports (1920 desktop, 1366 laptop, 820 tablet, 390 mobile).
Pick a viewport tab per screen; click an image for full size. Numbers come from <code>fixtures/sales_sample.csv</code>; agent text is illustrative.</p>
<div class="cols">
<div class="card"><h3>Automated checks</h3><p>{len(SCREENS)} screens × {len(VIEWPORTS)} viewports = {len(SCREENS) * len(VIEWPORTS)} captures. Result: <span class="pill {"ok" if ALL_OK else "bad"}">{"0 findings" if ALL_OK else "findings present"}</span></p>
<ul><li>horizontal page overflow</li><li>clipped / off-screen elements</li><li>overlapping chart and canvas labels</li><li>text contrast (WCAG 2.1 AA, computed from rendered colours)</li><li>chart / lane label size ≥ 10 px as rendered (qa_extra.py)</li><li>responsive navigation: rail left ≥768 px, bottom tabs &lt;768 px, 3 links, 1 active</li><li>mobile usability: nav targets ≥ 44 px, controls ≥ 32 px, no text &lt; 10 px</li></ul></div>
<div class="card"><h3>Not covered by automation — please judge</h3><ul><li>overall look and visual hierarchy</li><li>information density vs. clutter</li><li>whether the correction loop reads clearly</li><li>copy tone and naming</li></ul></div>
<div class="card"><h3>Known limits</h3><ul><li>Static HTML, not Streamlit; pixel parity is not expected</li><li>Animations visible only in live HTML (<code>pages/livewire-*.html</code>)</li><li>Light theme only; Plotly interactions not depicted</li><li>Currency ₹ is cosmetic</li></ul></div>
</div></section>
<section id="checks" class="screen"><h2>Viewport check matrix</h2>{"".join(matrix)}</section>
<section id="tokens-notes" class="screen"><h2>Design tokens &amp; consistency notes</h2>
<div class="sw">{sw}</div>
<div class="cols">
<div class="card"><h3>Consistent across all screens</h3><ul><li>Same rail, toolbar, pane header and 3 px radius</li><li>Teal = active/primary, green = verified, gold = feedback/test, coral = error/unapproved</li><li>Every status has a text label or icon, never colour alone</li><li>Tabular numerals for KPIs, ledgers and tables</li><li>Cost always reads "Pricing not configured"</li></ul></div>
<div class="card"><h3>Responsive behaviour</h3><ul><li>≥1400: three-pane layouts, horizontal lanes</li><li>1024–1399: narrower side panes</li><li>768–1023: single column; vertical lanes</li><li>&lt;768: bottom tab bar, 2-up KPI strip, narrow chart variants, tables scroll in-pane</li></ul></div>
<div class="card"><h3>Runtime-honesty rules shown in the design</h3><ul><li>Counter = counted agent messages only (task/events excluded)</li><li>Repair/feedback edges animate once per real event</li><li>Human stage is separate from Reviewer approval</li><li>Fault injection is badged and never shown as natural</li><li>No timers or progress percentages anywhere</li></ul></div>
</div>
<p class="note">Full token table with computed contrast ratios: <a href="#tokens">tokens screen</a> or <code>pages/tokens.html</code>.</p></section>
{"".join(secs)}
</main></body></html>"""


# ----------------------------------------------------------------------------- PDF
PAGE_W_MM, PAGE_H_MM, MARGIN_MM = 297.0, 210.0, 8.0
CONTENT_W = PAGE_W_MM - 2 * MARGIN_MM
CONTENT_H = PAGE_H_MM - 2 * MARGIN_MM - 14  # room for the caption line


def slices(path: Path, css_chunk: int, tmp: Path, tag: str) -> list[Path]:
    im = Image.open(path).convert("RGB")
    step = css_chunk * SCALE
    out = []
    for i, top in enumerate(range(0, im.height, step)):
        part = im.crop((0, top, im.width, min(top + step, im.height)))
        p = tmp / f"{tag}-{i}.jpg"
        part.save(p, quality=88)
        out.append(p)
    return out


def build_pdf(pdf_path: Path) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="dp-review-"))
    pages: list[str] = []

    def page(title: str, body: str) -> None:
        pages.append(f'<section class="pg"><div class="cap">{title}</div>{body}</section>')

    # cover + summary
    rows = "".join(
        f"<tr><td>{escape(label)}</td>"
        + "".join(
            f'<td class="{"ok" if (CHECKS[s][v]["overflowX"] <= 0 and not (CHECKS[s][v]["clipped"] or CHECKS[s][v]["overlaps"] or CHECKS[s][v]["contrast"] or CHECKS[s][v]["offscreen"])) else "bad"}">'
            f"{'pass' if (CHECKS[s][v]['overflowX'] <= 0 and not (CHECKS[s][v]['clipped'] or CHECKS[s][v]['overlaps'] or CHECKS[s][v]['contrast'] or CHECKS[s][v]['offscreen'])) else 'FINDINGS'}</td>"
            for v in VIEWPORTS
        )
        + "</tr>"
        for s, label in SCREENS
    )
    pages.append(
        f"""<section class="pg cover"><h1>DataPilot — UI Review (Light theme)</h1>
<p>M2 mockups · {date.today().isoformat()} · design only; no Streamlit shell, theme or Livewire code exists yet.</p>
<p>Screens: Ask &amp; Explore, Insights Studio, Agent Livewire (8 states), design tokens — at 1920 / 1366 / 820 / 390 px.
Numbers derive from <code>fixtures/sales_sample.csv</code>; agent text is illustrative.</p>
<table><thead><tr><th>Screen</th>{"".join(f"<th>{VP_LABEL[v]}</th>" for v in VIEWPORTS)}</tr></thead><tbody>{rows}</tbody></table>
<p class="small">Automated checks: horizontal overflow, clipped/off-screen elements, overlapping SVG labels, rendered-text contrast (WCAG 2.1 AA). They do not judge aesthetics — that is the reviewer's call.
Interactive version: <code>DataPilot_UI_Review_Light.html</code>. Desktop pages use full width; mobile pages are sliced into columns (continued left to right).</p></section>"""
    )

    for stem, label in SCREENS:
        for vp, css_w, max_cols in (
            ("desktop-1920", 1920, 1),
            ("laptop-1366", 1366, 1),
            ("tablet-820", 820, 3),
            ("mobile-390", 390, 4),
        ):
            path = img(stem, vp)
            height = Image.open(path).height // SCALE
            vp_label = VP_LABEL[vp]
            # choose the fewest columns that fit the whole screen on one page; else paginate
            cols = max_cols
            for k in range(1, max_cols + 1):
                width_k = (CONTENT_W - 3 * (k - 1)) / k
                if k * (CONTENT_H / width_k * css_w) >= height / (1.4 if k == 1 else 1.0):
                    cols = k
                    break
            col_w = (CONTENT_W - 3 * (cols - 1)) / cols
            chunk = (
                int(CONTENT_H / col_w * css_w)
                if cols > 1 or height > CONTENT_H / col_w * css_w * 1.1
                else height
            )
            parts = slices(path, chunk, tmp, f"{stem}-{vp}")
            per_page = cols
            for n in range(0, len(parts), per_page):
                group = parts[n : n + per_page]
                if len(parts) > 1 and cols == 1:
                    title = f"{escape(label)} · {vp_label} · part {n + 1} of {len(parts)}"
                elif len(parts) == 1:
                    title = f"{escape(label)} · {vp_label}"
                else:
                    title = (
                        f"{escape(label)} · {vp_label} · segments {n + 1}–{n + len(group)} of "
                        f"{len(parts)} (read left to right)"
                    )
                style = f"max-height:{CONTENT_H}mm;" if cols == 1 else ""
                body = "".join(
                    f'<img src="{p.as_uri()}" style="width:{col_w}mm;{style}object-fit:contain;object-position:top left">'
                    for p in group
                )
                page(title, f'<div class="row">{body}</div>')

    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
@page{{size:A4 landscape;margin:{MARGIN_MM}mm}}
*{{box-sizing:border-box}}body{{margin:0;background:#f7f6f2;color:#233247;font:11px/1.45 "Segoe UI",Arial,sans-serif;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
.pg{{page-break-after:always;height:{PAGE_H_MM - 2 * MARGIN_MM - 1}mm;overflow:hidden;background:#f7f6f2}}
.cap{{height:12mm;font-size:12px;font-weight:600;color:#077a86;border-bottom:1px solid #dde2e7;margin-bottom:2mm;padding-top:1mm}}
img{{display:block;border:1px solid #dde2e7}}.row{{display:flex;gap:3mm;align-items:flex-start}}
.cover h1{{font-size:26px;margin:10mm 0 4mm}}.cover table{{border-collapse:collapse;margin:6mm 0;width:100%;font-size:11px}}
.cover th,.cover td{{border-bottom:1px solid #dde2e7;padding:3px 8px;text-align:left}}
td.ok{{color:#1a6b55}}td.bad{{color:#a8323f;font-weight:700}}.small{{color:#566679;font-size:10px}}code{{color:#077a86}}
</style></head><body>{"".join(pages)}</body></html>"""
    tmp_html = tmp / "review-print.html"
    tmp_html.write_text(html, encoding="utf-8")
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="msedge")
        except Exception:
            browser = pw.chromium.launch()
        page_ = browser.new_page()
        page_.goto(tmp_html.as_uri())
        page_.wait_for_load_state("load")
        page_.pdf(
            path=str(pdf_path),
            format="A4",
            landscape=True,
            print_background=True,
            margin={
                "top": f"{MARGIN_MM}mm",
                "bottom": f"{MARGIN_MM}mm",
                "left": f"{MARGIN_MM}mm",
                "right": f"{MARGIN_MM}mm",
            },
        )
        browser.close()
    sys.stdout.write(f"pdf pages: {len(pages)}\n")


def build_gallery() -> str:
    figs = ""
    for stem, label in SCREENS:
        links = " · ".join(
            f'<a href="png/{stem}__{vp}.png" target="_blank" rel="noopener">{VP_LABEL[vp].split()[1]}</a>'
            for vp in VIEWPORTS
        )
        figs += (
            f'<figure><a href="pages/{stem}.html"><img src="png/{stem}__desktop-1920.png" loading="lazy" alt="{escape(label)} desktop"></a>'
            f'<figcaption><b>{escape(label)}</b><br>PNG: {links} · <a href="pages/{stem}.html">live page</a></figcaption></figure>'
        )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DataPilot UI Gallery (Light)</title><style>
body{{margin:0;background:#f7f6f2;color:#233247;font:14px/1.5 "Segoe UI",system-ui,sans-serif;padding:24px 28px}}
h1{{font:700 22px Georgia,serif;margin:0 0 4px}}p{{color:#566679;margin:0 0 18px}}a{{color:#077a86}}
.gal{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:16px}}
figure{{margin:0;background:#fff;border:1px solid #dde2e7;border-radius:3px;padding:8px}}
img{{width:100%;height:auto;display:block;border:1px solid #dde2e7;aspect-ratio:16/10;object-fit:cover;object-position:top}}
figcaption{{padding:8px 2px 2px;font-size:13px;color:#566679}}figcaption b{{color:#233247}}
</style></head><body><h1>DataPilot — Light theme gallery</h1>
<p>Desktop thumbnails (top of page). Open a size-specific PNG or the live, resizable page. Interactive review: <a href="DataPilot_UI_Review_Light.html">DataPilot_UI_Review_Light.html</a> · PDF: <a href="DataPilot_UI_Review_Light.pdf">DataPilot_UI_Review_Light.pdf</a></p>
<div class="gal">{figs}</div></body></html>"""


def main() -> int:
    (HERE / "gallery.html").write_text(build_gallery(), encoding="utf-8")
    (HERE / "DataPilot_UI_Review_Light.html").write_text(build_html(), encoding="utf-8")
    build_pdf(HERE / "DataPilot_UI_Review_Light.pdf")
    sys.stdout.write(f"all checks clean: {ALL_OK}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

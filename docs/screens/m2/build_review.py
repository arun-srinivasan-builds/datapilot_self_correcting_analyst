"""Build DataPilot_M2_Actual_UI_Review.pdf from the screenshots of the ACTUAL running Streamlit app.

    .venv\\Scripts\\python docs/screens/m2/build_review.py

Screenshots are produced by tests/ui/test_browser.py (Playwright, real server). Nothing here is a mockup.
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
OUT = HERE / "DataPilot_M2_Actual_UI_Review.pdf"
RESULTS = json.loads((HERE / "test-results.json").read_text(encoding="utf-8"))

PAGE_W, PAGE_H, MARGIN = 297.0, 210.0, 8.0
CW = PAGE_W - 2 * MARGIN
CH = PAGE_H - 2 * MARGIN - 20  # caption band
VP = {
    "desktop-1920": ("Desktop 1920", 1920),
    "laptop-1366": ("Laptop 1366", 1366),
    "tablet-820": ("Tablet 820", 820),
    "mobile-390": ("Mobile 390", 390),
}
NONLIVE = "DESIGN PREVIEW · NON-LIVE · scripted events, not AutoGen execution"

STATES = [
    ("livewire-idle", "Livewire · idle (genuine: no run exists)", False),
    ("livewire-running", "Livewire · running", True),
    ("livewire-exec-error", "Livewire · execution error", True),
    ("livewire-repair", "Livewire · repair", True),
    ("livewire-feedback", "Livewire · Reviewer feedback", True),
    ("livewire-approved", "Livewire · Reviewer approved (human pending)", True),
    ("livewire-limit", "Livewire · limit reached (unapproved)", True),
    ("livewire-fault", "Livewire · fault injection (TEST ONLY)", True),
]
REPRESENTATIVE = {"livewire-repair", "livewire-approved", "livewire-fault", "livewire-limit"}


def slices(path: Path, css_chunk: int, tmp: Path, tag: str) -> list[Path]:
    im = Image.open(path).convert("RGB")
    out = []
    for i, top in enumerate(range(0, im.height, css_chunk)):
        p = tmp / f"{tag}-{i}.jpg"
        im.crop((0, top, im.width, min(top + css_chunk, im.height))).save(p, quality=90)
        out.append(p)
    return out


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="dp-m2-"))
    pages: list[str] = []

    def add(caption: str, body: str, nonlive: bool = False) -> None:
        badge = f'<span class="b nl">{escape(NONLIVE)}</span>' if nonlive else ""
        pages.append(
            f'<section class="pg"><div class="cap"><span>{escape(caption)}</span>'
            f'<span class="b act">ACTUAL STREAMLIT APP</span>{badge}</div>{body}</section>'
        )

    def shots(stem: str, label: str, viewports: list[str], nonlive: bool) -> None:
        for vp in viewports:
            path = HERE / f"{stem}-{vp}.png"
            name, css_w = VP[vp]
            height = Image.open(path).height
            cols_max = {"desktop-1920": 1, "laptop-1366": 1, "tablet-820": 3, "mobile-390": 4}[vp]
            cols = cols_max
            for k in range(1, cols_max + 1):
                width_k = (CW - 3 * (k - 1)) / k
                if k * (CH / width_k * css_w) >= height / (1.4 if k == 1 else 1.0):
                    cols = k
                    break
            col_w = (CW - 3 * (cols - 1)) / cols
            fit = CH / col_w * css_w
            chunk = int(fit) if (cols > 1 or height > fit * 1.4) else height
            parts = slices(path, chunk, tmp, f"{stem}-{vp}")
            for n in range(0, len(parts), cols):
                group = parts[n : n + cols]
                suffix = (
                    ""
                    if len(parts) == 1
                    else f" · segment {n + 1}–{n + len(group)} of {len(parts)}"
                )
                imgs = "".join(
                    f'<img src="{p.as_uri()}" style="width:{col_w}mm;max-height:{CH}mm;object-fit:contain;'
                    f'object-position:top left">'
                    for p in group
                )
                add(f"{label} · {name}{suffix}", f'<div class="row">{imgs}</div>', nonlive)

    r = RESULTS
    rows = "".join(
        f"<tr><td>{escape(a)}</td><td class='n'>{b}</td><td>{escape(c)}</td></tr>"
        for a, b, c in r["suites"]
    )
    pages.append(
        f"""<section class="pg cover"><h1>DataPilot — M2 actual UI review</h1>
<p class="lead">Screenshots of the <b>actual running Streamlit application</b> (not the HTML mockups), captured by the automated
browser suite on {date.today().isoformat()}. Four viewports: desktop 1920, laptop 1366, tablet 820, mobile 390.</p>
<div class="warn"><b>Non-live labelling.</b> Until M3 there is no AutoGen execution. Every Livewire state except <i>idle</i> and
the Insights Studio results are a <b>design preview</b>: scripted events pushed through the real event model and reducer, with a
persistent banner, a toolbar chip and “not AI output” notes. No token usage or cost is shown; exports are disabled.</div>
<h2>Validation results</h2>
<table><thead><tr><th>Suite</th><th>Tests</th><th>Scope</th></tr></thead><tbody>{rows}</tbody></table>
<p class="res"><b>Total {r["passed"]} passed, {r["failed"]} failed.</b> Coverage {r["coverage"]}%.
Ruff: {escape(r["ruff"])}. Browser QA: {escape(r["browser"])}</p>
<h2>Contents</h2>
<p class="small">Ask &amp; Explore (loaded dataset) and Insights Studio at all four viewports · all eight Livewire states at desktop ·
repair, approved, limit-reached and fault-injection at laptop, tablet and mobile.</p>
<h2>Known limitations</h2><ul class="small">{"".join(f"<li>{escape(x)}</li>" for x in r["limitations"])}</ul></section>"""
    )

    all_vps = list(VP)
    shots("explore", "Ask & Explore · loaded dataset", all_vps, False)
    shots("insights", "Insights Studio · analytical results", all_vps, True)
    for stem, label, nonlive in STATES:
        shots(stem, label, ["desktop-1920"], nonlive)
    for stem, label, nonlive in STATES:
        if stem in REPRESENTATIVE:
            shots(stem, label, ["laptop-1366", "tablet-820", "mobile-390"], nonlive)

    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
@page{{size:A4 landscape;margin:{MARGIN}mm}}*{{box-sizing:border-box}}
body{{margin:0;background:#f7f6f2;color:#233247;font:11px/1.45 "Segoe UI",Arial,sans-serif;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
.pg{{page-break-after:always;height:{PAGE_H - 2 * MARGIN - 1}mm;overflow:hidden}}
.cap{{height:16mm;display:flex;gap:8px;align-items:center;flex-wrap:wrap;border-bottom:1px solid #dde2e7;margin-bottom:2mm;font-size:12px;font-weight:600;color:#077a86}}
.b{{font-size:9px;letter-spacing:.05em;padding:2px 7px;border-radius:3px;font-weight:700}}
.act{{background:#e2f1f2;color:#065a63;border:1px solid #9ccfd4}}
.nl{{background:#fbf3e0;color:#7d5a12;border:1.5px dashed #b58429}}
img{{display:block;border:1px solid #dde2e7}}.row{{display:flex;gap:3mm;align-items:flex-start}}
.cover h1{{font:700 26px Georgia,serif;margin:6mm 0 3mm}}.cover h2{{font-size:13px;margin:5mm 0 2mm}}
.lead{{font-size:12px;max-width:230mm}}.warn{{background:#fbf3e0;border-left:4px solid #b58429;padding:3mm 4mm;margin:3mm 0;font-size:11px}}
table{{border-collapse:collapse;width:100%;font-size:10.5px}}th,td{{border-bottom:1px solid #dde2e7;padding:2px 8px;text-align:left}}
th{{background:#f1f3f5;color:#566679}}td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.res{{margin:2mm 0}}.small{{font-size:10.5px;color:#566679}}ul.small{{margin:0;padding-left:5mm}}
</style></head><body>{"".join(pages)}</body></html>"""
    page_html = tmp / "review.html"
    page_html.write_text(html, encoding="utf-8")
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="msedge")
        except Exception:
            browser = pw.chromium.launch()
        pg = browser.new_page()
        pg.goto(page_html.as_uri())
        pg.wait_for_load_state("load")
        pg.pdf(
            path=str(OUT),
            format="A4",
            landscape=True,
            print_background=True,
            margin={
                "top": f"{MARGIN}mm",
                "bottom": f"{MARGIN}mm",
                "left": f"{MARGIN}mm",
                "right": f"{MARGIN}mm",
            },
        )
        browser.close()
    sys.stdout.write(f"{OUT} · {len(pages)} pages\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

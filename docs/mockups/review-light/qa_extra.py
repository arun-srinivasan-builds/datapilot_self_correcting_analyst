"""Extra QA gates for the light mockups: chart-label readability, responsive navigation, mobile usability.

Writes review-light/qa_extra.json and prints a summary. Complements capture_light.py (overflow,
clipping, overlap, contrast).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PAGES = HERE / "pages"
VIEWPORTS = {
    "desktop-1920": (1920, 1080),
    "laptop-1366": (1366, 768),
    "tablet-820": (820, 1180),
    "mobile-390": (390, 844),
}
STEMS = ["ask-explore", "insights-studio", "tokens"] + [
    f"livewire-{s}"
    for s in (
        "idle",
        "running",
        "exec-error",
        "repair",
        "reviewer-feedback",
        "approved",
        "limit-reached",
        "fault-injection",
    )
]

JS = r"""
() => {
  const out = {chartMin: null, chartSmall: [], nav: {}, targets: [], tinyText: []};
  // chart text effective size = font-size * rendered scale of its svg
  document.querySelectorAll('.chart svg').forEach(svg => {
    const r = svg.getBoundingClientRect(); if (r.width === 0) return;
    const vb = svg.viewBox.baseVal; const k = r.width / vb.width;
    svg.querySelectorAll('text').forEach(t => {
      const fs = parseFloat(getComputedStyle(t).fontSize) * k;
      out.chartMin = out.chartMin === null ? fs : Math.min(out.chartMin, fs);
      if (fs < 10.5) out.chartSmall.push((t.textContent || '').trim().slice(0, 24) + ' ' + fs.toFixed(1) + 'px');
    });
  });
  // flow svg label sizes
  document.querySelectorAll('.lanes svg').forEach(svg => {
    const r = svg.getBoundingClientRect(); if (r.width === 0) return;
    const k = r.width / svg.viewBox.baseVal.width;
    svg.querySelectorAll('text').forEach(t => {
      const fs = parseFloat(getComputedStyle(t).fontSize) * k;
      if (fs < 9.5) out.chartSmall.push('lanes:' + (t.textContent || '').trim().slice(0, 24) + ' ' + fs.toFixed(1) + 'px');
    });
  });
  // navigation
  const rail = document.querySelector('.rail'); const rr = rail.getBoundingClientRect();
  const links = [...rail.querySelectorAll('a.nav')];
  out.nav = {
    links: links.length, hrefs: links.map(a => a.getAttribute('href')),
    active: links.filter(a => a.classList.contains('is-active')).length,
    position: getComputedStyle(rail).position,
    rect: [Math.round(rr.left), Math.round(rr.top), Math.round(rr.width), Math.round(rr.height)],
    inViewport: rr.bottom <= window.innerHeight + 1 && rr.top >= -1 && rr.right <= window.innerWidth + 1,
    minTarget: Math.min(...links.map(a => { const b = a.getBoundingClientRect(); return Math.min(b.width, b.height); })),
  };
  // touch targets
  document.querySelectorAll('.btn, .seg span, textarea, .select, .rail a.nav, .state-nav a').forEach(el => {
    const b = el.getBoundingClientRect(); if (b.width === 0) return;
    out.targets.push({cls: el.closest('.state-nav') ? 'state-nav' : (el.className || el.tagName), h: Math.round(b.height), w: Math.round(b.width), t: (el.textContent || '').trim().slice(0, 20)});
  });
  // tiny html text
  document.querySelectorAll('body *').forEach(el => {
    if (el.closest('svg')) return;
    if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    if (fs < 10) out.tinyText.push((el.textContent || '').trim().slice(0, 24) + ' ' + fs + 'px');
  });
  return out;
}
"""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    results: dict[str, dict] = {}
    failures: list[str] = []
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="msedge")
        except Exception:
            browser = pw.chromium.launch()
        for vp, (w, h) in VIEWPORTS.items():
            ctx = browser.new_context(viewport={"width": w, "height": h}, has_touch=w < 768)
            page = ctx.new_page()
            for stem in STEMS:
                page.goto((PAGES / f"{stem}.html").as_uri())
                r = page.evaluate(JS)
                results.setdefault(stem, {})[vp] = r
                tag = f"{stem}@{vp}"
                if r["chartSmall"]:
                    failures.append(f"{tag}: small chart/lane labels {r['chartSmall'][:3]}")
                if r["tinyText"]:
                    failures.append(f"{tag}: text under 10px {r['tinyText'][:3]}")
                nav = r["nav"]
                if nav["links"] != 3 or nav["active"] != 1:
                    failures.append(f"{tag}: nav links={nav['links']} active={nav['active']}")
                if not nav["inViewport"]:
                    failures.append(f"{tag}: rail not inside viewport {nav['rect']}")
                if w < 768:
                    if nav["position"] != "fixed" or nav["rect"][3] > 80:
                        failures.append(f"{tag}: mobile nav should be a bottom tab bar {nav}")
                    if nav["minTarget"] < 44:
                        failures.append(f"{tag}: nav touch target {nav['minTarget']}px < 44")
                    for t in r["targets"]:
                        if "state-nav" in str(t["cls"]):
                            continue
                        if t["h"] < 32:
                            failures.append(f"{tag}: control '{t['t']}' is {t['h']}px tall (<32)")
                elif nav["rect"][2] > 80:
                    failures.append(f"{tag}: desktop rail too wide {nav['rect']}")
            ctx.close()
        browser.close()
    (HERE / "qa_extra.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    for f in sorted(set(failures)):
        sys.stdout.write(f + "\n")
    mins = [r["chartMin"] for per in results.values() for r in per.values() if r["chartMin"]]
    sys.stdout.write(
        f"checked {len(STEMS)} screens x {len(VIEWPORTS)} viewports; {len(set(failures))} findings; "
        f"smallest chart label {min(mins):.1f}px\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

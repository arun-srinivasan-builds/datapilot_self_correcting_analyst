"""Capture every mockup screen at four viewports and run objective visual checks.

Writes docs/mockups/review-light/png/<screen>__<viewport>.png and review/checks.json.
Checks (per screen x viewport): horizontal page overflow, clipped text (visible overflow),
overlapping SVG labels, and text contrast against the effective background (WCAG 2.1).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

REVIEW = Path(__file__).resolve().parent
MOCK = REVIEW / "pages"
PNG = REVIEW / "png"
SCALE = 2

VIEWPORTS = {
    "desktop-1920": (1920, 1080),
    "laptop-1366": (1366, 768),
    "tablet-820": (820, 1180),
    "mobile-390": (390, 844),
}
LIVEWIRE_STATES = [
    "idle",
    "running",
    "exec-error",
    "repair",
    "reviewer-feedback",
    "approved",
    "limit-reached",
    "fault-injection",
]
SCREENS = (
    [("ask-explore", "Ask & Explore"), ("insights-studio", "Insights Studio")]
    + [(f"livewire-{s}", f"Agent Livewire · {s.replace('-', ' ')}") for s in LIVEWIRE_STATES]
    + [("tokens", "Design tokens")]
)

CHECK_JS = r"""
() => {
  const out = {overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
               clipped: [], overlaps: [], contrast: [], offscreen: []};
  const parse = c => { const m = c && c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(',').map(s => parseFloat(s)); return {r:p[0], g:p[1], b:p[2], a:p.length>3?p[3]:1}; };
  const lum = c => { const f = v => { v/=255; return v<=0.03928? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); };
    return 0.2126*f(c.r)+0.7152*f(c.g)+0.0722*f(c.b); };
  const ratio = (a,b) => { const x=lum(a), y=lum(b); return (Math.max(x,y)+0.05)/(Math.min(x,y)+0.05); };
  const bgOf = el => { while (el) { const s = getComputedStyle(el); const c = parse(s.backgroundColor);
    if (c && c.a > 0.5) return c; el = el.parentElement; } return {r:247,g:246,b:242,a:1}; };
  const label = el => (el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className) + ' "' +
    (el.textContent||'').trim().slice(0,40) + '"';
  const inScroll = el => { for (let p = el.parentElement; p; p = p.parentElement) {
    const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll') return true; } return false; };

  // clipped / overflowing text (visible overflow outside scroll containers)
  document.querySelectorAll('body *').forEach(el => {
    if (el.closest('svg') || inScroll(el)) return;
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') return;
    if (el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0 && (s.overflowX === 'visible' || s.overflowX === 'hidden'))
      out.clipped.push(label(el) + ' sw=' + el.scrollWidth + ' cw=' + el.clientWidth);
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.right > window.innerWidth + 1) out.offscreen.push(label(el) + ' right=' + Math.round(r.right));
  });

  // overlapping svg labels
  document.querySelectorAll('svg').forEach(svg => {
    const cs = getComputedStyle(svg); if (cs.display === 'none' || svg.getBoundingClientRect().width === 0) return;
    const texts = [...svg.querySelectorAll('text')].filter(t => (t.textContent||'').trim());
    const boxes = texts.map(t => ({t, r: t.getBoundingClientRect()}));
    for (let i = 0; i < boxes.length; i++) for (let j = i+1; j < boxes.length; j++) {
      const a = boxes[i].r, b = boxes[j].r;
      const w = Math.min(a.right,b.right) - Math.max(a.left,b.left), h = Math.min(a.bottom,b.bottom) - Math.max(a.top,b.top);
      if (w > 2 && h > 3) out.overlaps.push('"' + boxes[i].t.textContent.trim() + '" x "' + boxes[j].t.textContent.trim() + '"');
    }
  });

  // contrast of text vs effective background
  const seen = new Set();
  const textEls = [...document.querySelectorAll('body *')].filter(el => {
    if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE') return false;
    return [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  });
  textEls.forEach(el => {
    const s = getComputedStyle(el); if (s.display === 'none' || s.visibility === 'hidden') return;
    if (el.closest('svg') && el.closest('svg').getBoundingClientRect().width === 0) return;
    let fg, bg;
    if (el.closest('svg')) {
      fg = parse(s.fill); const g = el.closest('g'); const rect = g && g.querySelector(':scope > rect');
      bg = rect ? parse(getComputedStyle(rect).fill) : bgOf(el.closest('svg').parentElement);
      if (rect && getComputedStyle(rect).fill === 'none') bg = bgOf(el.closest('svg').parentElement);
    } else { fg = parse(s.color); bg = bgOf(el); }
    if (!fg || !bg) return;
    const size = parseFloat(s.fontSize), bold = parseInt(s.fontWeight) >= 700;
    const need = (size >= 24 || (size >= 18.66 && bold)) ? 3 : 4.5;
    const r = ratio(fg, bg);
    const key = label(el);
    if (r < need && !seen.has(key)) { seen.add(key); out.contrast.push(key + ' ' + r.toFixed(2) + ':1 (<' + need + ')'); }
  });
  return out;
}
"""


def main() -> int:
    PNG.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, dict]] = {}
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="msedge")
        except Exception:
            browser = pw.chromium.launch()
        for vp, (w, h) in VIEWPORTS.items():
            ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=SCALE)
            page = ctx.new_page()
            for stem, _ in SCREENS:
                page.set_viewport_size({"width": w, "height": h})
                page.goto((MOCK / f"{stem}.html").as_uri())
                page.wait_for_load_state("load")
                res = page.evaluate(CHECK_JS)
                res["pageHeight"] = page.evaluate("document.documentElement.scrollHeight")
                results.setdefault(stem, {})[vp] = res
                if w > 767:  # full-page capture: let the sticky rail span the page
                    page.add_style_tag(
                        content=".rail{position:static!important;height:auto!important}"
                    )
                else:  # fixed bottom tab bar must land at the page end
                    page.set_viewport_size({"width": w, "height": int(res["pageHeight"])})
                page.screenshot(path=str(PNG / f"{stem}__{vp}.png"), full_page=True)
            ctx.close()
        browser.close()
    (REVIEW / "checks.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    bad = 0
    for stem, per in results.items():
        for vp, r in per.items():
            issues = (
                r["overflowX"] > 0
                or r["clipped"]
                or r["overlaps"]
                or r["contrast"]
                or r["offscreen"]
            )
            if issues:
                bad += 1
                sys.stdout.write(
                    f"{stem} @ {vp}: overflowX={r['overflowX']} clipped={len(r['clipped'])} "
                    f"overlaps={len(r['overlaps'])} contrast={len(r['contrast'])} offscreen={len(r['offscreen'])}\n"
                )
                for k in ("clipped", "overlaps", "contrast", "offscreen"):
                    for item in r[k][:6]:
                        sys.stdout.write(f"    {k}: {item}\n")
    sys.stdout.write(
        f"checked {len(results)} screens x {len(VIEWPORTS)} viewports; {bad} with findings\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

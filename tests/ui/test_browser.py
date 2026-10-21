"""Browser smoke + responsive QA against the real running Streamlit app (marker: ui).

Per viewport (1920 / 1366 / 820 / 390) it walks Ask & Explore, the Livewire design-preview states and
Insights Studio, saves screenshots to docs/screens/m2/ and asserts: no horizontal overflow, no clipped or
off-screen elements, no overlapping chart labels, AA text contrast, readable chart labels, working
navigation (rail >=768px, bottom tabs <768px) and usable mobile controls.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import Page, sync_playwright  # noqa: E402

pytestmark = pytest.mark.ui

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "datapilot" / "ui" / "app.py"
SHOTS = ROOT / "docs" / "screens" / "m2"
VIEWPORTS = {
    "desktop-1920": (1920, 1080),
    "laptop-1366": (1366, 768),
    "tablet-820": (820, 1180),
    "mobile-390": (390, 844),
}

CHECK_JS = r"""
() => {
  const out = {overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
               clipped: [], overlaps: [], contrast: [], offscreen: [], smallLabels: [], nav: {}, targets: []};
  const parse = c => { const m = c && c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(',').map(s => parseFloat(s)); return {r:p[0], g:p[1], b:p[2], a:p.length>3?p[3]:1}; };
  const lum = c => { const f = v => { v/=255; return v<=0.03928? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); };
    return 0.2126*f(c.r)+0.7152*f(c.g)+0.0722*f(c.b); };
  const ratio = (a,b) => { const x=lum(a), y=lum(b); return (Math.max(x,y)+0.05)/(Math.min(x,y)+0.05); };
  const bgOf = el => { while (el) { const s = getComputedStyle(el); const c = parse(s.backgroundColor);
    if (c && c.a > 0.5) return c; el = el.parentElement; } return {r:247,g:246,b:242,a:1}; };
  const label = el => ((el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className) + '').slice(0,40)
    + ' "' + (el.textContent||'').trim().slice(0,36) + '"';
  const shown = el => { const s = getComputedStyle(el); const r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0; };
  const main = document.querySelector('[data-testid="stMain"]') || document.body;
  const inScroll = el => { for (let p = el.parentElement; p && p !== main; p = p.parentElement) {
    const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll') return true; } return false; };

  main.querySelectorAll('*').forEach(el => {
    if (el.closest('svg') || el.closest('[data-testid="stTooltipContent"]') || !shown(el) || inScroll(el)) return;
    const s = getComputedStyle(el);
    if (el.scrollWidth > el.clientWidth + 1 && s.overflowX === 'visible' && el.clientWidth > 0
        && !el.closest('[data-baseweb="select"]') && !el.closest('[data-testid="stFileUploader"]'))
      out.clipped.push(label(el) + ' sw=' + el.scrollWidth + ' cw=' + el.clientWidth);
    const r = el.getBoundingClientRect();
    if (r.right > window.innerWidth + 1) out.offscreen.push(label(el) + ' right=' + Math.round(r.right));
  });

  document.querySelectorAll('svg').forEach(svg => {
    if (!shown(svg)) return;
    const texts = [...svg.querySelectorAll('text')].filter(t => (t.textContent||'').trim());
    const boxes = texts.map(t => ({t, r: t.getBoundingClientRect()}));
    for (let i = 0; i < boxes.length; i++) for (let j = i+1; j < boxes.length; j++) {
      const a = boxes[i].r, b = boxes[j].r;
      const w = Math.min(a.right,b.right) - Math.max(a.left,b.left), h = Math.min(a.bottom,b.bottom) - Math.max(a.top,b.top);
      if (w > 2 && h > 3) out.overlaps.push('"' + boxes[i].t.textContent.trim() + '" x "' + boxes[j].t.textContent.trim() + '"');
    }
    const vb = svg.viewBox.baseVal; if (!vb || !vb.width) return;
    const k = svg.getBoundingClientRect().width / vb.width;
    const inLanes = !!svg.closest('.lanes');
    texts.forEach(t => { const fs = parseFloat(getComputedStyle(t).fontSize) * k;
      if (fs < (inLanes ? 9.5 : 10.5)) out.smallLabels.push((t.textContent||'').trim().slice(0,24) + ' ' + fs.toFixed(1) + 'px'); });
  });

  const seen = new Set();
  [...main.querySelectorAll('*')].filter(el => [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())).forEach(el => {
    if (!shown(el) || el.closest('button:disabled') || el.closest('[disabled]') || el.closest('[aria-disabled="true"]')) return;
    if (el.closest('svg') && !shown(el.closest('svg'))) return;
    const s = getComputedStyle(el); let fg, bg;
    if (el.closest('svg')) {
      fg = parse(s.fill); const g = el.closest('g'); const rect = g && g.querySelector(':scope > rect');
      bg = rect && getComputedStyle(rect).fill !== 'none' ? parse(getComputedStyle(rect).fill) : bgOf(el.closest('svg').parentElement);
    } else { fg = parse(s.color); bg = bgOf(el); }
    if (!fg || !bg) return;
    const size = parseFloat(s.fontSize), bold = parseInt(s.fontWeight) >= 700;
    const need = (size >= 24 || (size >= 18.66 && bold)) ? 3 : 4.5;
    const r = ratio(fg, bg), key = label(el);
    if (r < need && !seen.has(key)) { seen.add(key); out.contrast.push(key + ' ' + r.toFixed(2) + ':1 (<' + need + ')'); }
  });

  const rail = document.querySelector('.st-key-rail'); const rr = rail.getBoundingClientRect();
  const btns = [...rail.querySelectorAll('button')].filter(shown);
  out.nav = {buttons: btns.length, active: btns.filter(b => b.getAttribute('data-testid') === 'stBaseButton-primary').length,
             position: getComputedStyle(rail).position, rect: [Math.round(rr.left), Math.round(rr.top), Math.round(rr.width), Math.round(rr.height)],
             inViewport: rr.bottom <= window.innerHeight + 1 && rr.right <= window.innerWidth + 1,
             minTarget: Math.min(...btns.map(b => { const r = b.getBoundingClientRect(); return Math.min(r.width, r.height); }))};
  main.querySelectorAll('button, textarea, input, [data-baseweb="select"]').forEach(el => {
    if (!shown(el) || el.closest('.st-key-rail') || el.disabled) return;
    const b = el.getBoundingClientRect(); out.targets.push({t: (el.textContent || el.placeholder || '').trim().slice(0, 24), h: Math.round(b.height)});
  });
  return out;
}
"""


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, test-only local server
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(APP),
            "--server.port",
            str(port),
            "--server.headless",
            "true",
            "--server.fileWatcherType",
            "none",
            "--browser.gatherUsageStats",
            "false",
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                if urllib.request.urlopen(f"{url}/_stcore/health", timeout=1).status == 200:  # noqa: S310
                    break
            except OSError:
                time.sleep(0.5)
        else:
            pytest.fail("streamlit server did not start")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _snap(page: Page, path: Path, height: int) -> None:
    full = page.evaluate(
        "Math.max(document.querySelector('[data-testid=\"stMain\"]').scrollHeight, window.innerHeight)"
    )
    width = page.viewport_size["width"]
    page.set_viewport_size({"width": width, "height": int(full)})
    page.wait_for_timeout(400)
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path))
    page.set_viewport_size({"width": width, "height": height})
    page.wait_for_timeout(300)


def _go(page: Page, ws: str) -> None:
    page.locator(f".st-key-nav-{ws} button:visible").first.click()
    page.wait_for_timeout(1400)


def _pick(page: Page, label: str) -> None:
    page.locator('[data-testid="stButtonGroup"] button', has_text=label).first.click()
    page.wait_for_timeout(1400)


def _findings(tag: str, r: dict, mobile: bool) -> list[str]:
    f: list[str] = []
    if r["overflowX"] > 0:
        f.append(f"{tag}: horizontal overflow {r['overflowX']}px")
    for key in ("clipped", "overlaps", "contrast", "offscreen", "smallLabels"):
        if r[key]:
            f.append(f"{tag}: {key}: {r[key][:3]}")
    nav = r["nav"]
    if nav["buttons"] != 3 or nav["active"] != 1 or not nav["inViewport"]:
        f.append(f"{tag}: navigation {nav}")
    if mobile:
        if nav["position"] != "fixed" or nav["rect"][3] > 80 or nav["minTarget"] < 44:
            f.append(f"{tag}: mobile nav is not a usable bottom bar {nav}")
        for t in r["targets"]:
            if t["h"] < 32:
                f.append(f"{tag}: control '{t['t']}' only {t['h']}px tall")
    elif nav["rect"][2] > 80:
        f.append(f"{tag}: rail too wide {nav['rect']}")
    return f


@pytest.mark.parametrize("vp", list(VIEWPORTS))
def test_viewport_walkthrough(server: str, vp: str) -> None:
    w, h = VIEWPORTS[vp]
    mobile = w < 768
    problems: list[str] = []
    console_errors: list[str] = []
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="msedge")
        except Exception:  # fall back to bundled chromium
            browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": w, "height": h})
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.goto(server)
        page.wait_for_selector(".st-key-rail", timeout=30000)
        page.wait_for_timeout(1500)

        def check(name: str) -> None:
            res = page.evaluate(CHECK_JS)
            problems.extend(_findings(f"{name}@{vp}", res, mobile))
            _snap(page, SHOTS / f"{name}-{vp}.png", h)

        check("explore-empty")
        page.locator('[data-testid="stSelectbox"]').first.click()
        page.get_by_role("option", name="sales_sample.csv").click()
        page.wait_for_timeout(2500)
        check("explore")
        _go(page, "livewire")
        check("livewire-idle")
        for label, tag in (
            ("Running", "running"),
            ("Execution error", "exec-error"),
            ("Repair", "repair"),
            ("Reviewer feedback", "feedback"),
            ("Reviewer approved", "approved"),
            ("Limit reached", "limit"),
            ("Fault injection", "fault"),
        ):
            _pick(page, label)
            check(f"livewire-{tag}")
        _pick(page, "Reviewer approved")
        _go(page, "insights")
        check("insights")
        _go(page, "explore")
        assert page.locator("text=sales_sample.csv").count() > 0  # dataset survived navigation
        browser.close()
    assert not problems, "\n".join(problems)
    real_errors = [e for e in console_errors if "favicon" not in e.lower()]
    assert not real_errors, real_errors[:3]

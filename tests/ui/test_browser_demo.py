"""Browser QA of the PUBLIC demo page at four viewports (marker: ui): no overflow, animation works,
native charts render, Run B shows the repair. Starts the real app in demo mode."""

from __future__ import annotations

import os
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
VIEWPORTS = {
    "desktop-1920": (1920, 1080),
    "laptop-1366": (1366, 768),
    "tablet-820": (820, 1180),
    "mobile-390": (390, 844),
}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def url() -> Iterator[str]:
    port = _free_port()
    env = {
        **os.environ,
        "DATAPILOT_MODE": "demo",
        "DATAPILOT_DEMO_DIR": str(ROOT / "demo_data"),
        "DATAPILOT_CONTAINER": "1",
        "PYTHONPATH": f"{ROOT / 'src'}{os.pathsep}{ROOT}",
    }
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "streamlit", "run", str(APP), "--server.port", str(port),
         "--server.headless", "true", "--browser.gatherUsageStats", "false"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    base = f"http://127.0.0.1:{port}"
    for _ in range(90):
        try:
            urllib.request.urlopen(f"{base}/_stcore/health", timeout=2)  # noqa: S310
            break
        except OSError:
            time.sleep(1)
    else:
        proc.terminate()
        pytest.fail("demo app did not start")
    yield base
    proc.terminate()


@pytest.fixture(scope="module")
def browser_page_factory() -> Iterator[object]:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield lambda w, h: browser.new_page(viewport={"width": w, "height": h})
        browser.close()


def _open(page: Page, base: str) -> None:
    page.goto(base)
    page.wait_for_selector("text=Four AI agents", timeout=60000)
    page.wait_for_timeout(1500)


@pytest.mark.parametrize("name", list(VIEWPORTS))
def test_demo_page_has_no_overflow_and_a_working_animation(url, browser_page_factory, name):
    w, h = VIEWPORTS[name]
    page = browser_page_factory(w, h)
    _open(page, url)
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0
    box = page.locator("iframe").first.bounding_box()
    assert box and box["width"] > 0.6 * min(w, 1120)  # the animation uses the page width
    frame = page.frame_locator("iframe").first
    frame.locator("#scrub").evaluate(
        "e => { e.value = e.max; e.dispatchEvent(new Event('input')) }"
    )
    page.wait_for_timeout(500)
    assert "Answer ready" in frame.locator("#ttl").inner_text()
    assert frame.locator("#cnt").inner_text() == "4"
    page.evaluate("document.querySelector('[class*=st-key-chartcard]').scrollIntoView()")
    page.wait_for_selector(".js-plotly-plot", timeout=30000)
    assert page.locator(".js-plotly-plot").count() == 2
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0
    page.close()


def test_run_b_shows_the_crash_and_the_repair(url, browser_page_factory):
    page = browser_page_factory(1366, 768)
    _open(page, url)
    page.get_by_text("Run B · Watch a mistake get fixed").first.click()
    page.wait_for_timeout(3000)
    frame = page.frame_locator("iframe").first
    frame.locator("#scrub").evaluate("e => { e.value = 3; e.dispatchEvent(new Event('input')) }")
    page.wait_for_timeout(400)
    assert "crashed" in frame.locator("#ttl").inner_text()
    assert "KeyError" in frame.locator("#det").inner_text()
    frame.locator("#scrub").evaluate("e => { e.value = 4; e.dispatchEvent(new Event('input')) }")
    page.wait_for_timeout(400)
    assert "fixes the program" in frame.locator("#ttl").inner_text()
    page.close()

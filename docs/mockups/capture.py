"""Screenshot every mockup page at 1920 and 390 (dev-only; Playwright + installed Microsoft Edge).

Also asserts no horizontal page overflow at each viewport, so the mockups themselves are responsive.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE / "png"
VIEWPORTS = {1920: (1920, 1080), 390: (390, 844)}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    pages = sorted(p for p in HERE.glob("*.html") if p.stem != "index") + [HERE / "index.html"]
    problems: list[str] = []
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="msedge")
        except Exception:  # fall back to bundled chromium if installed
            browser = pw.chromium.launch()
        for width, (w, h) in VIEWPORTS.items():
            ctx = browser.new_context(viewport={"width": w, "height": h})
            page = ctx.new_page()
            for html in pages:
                page.goto(html.as_uri())
                page.wait_for_load_state("load")
                if width > 767:  # make the sticky rail span the full-page capture
                    page.add_style_tag(
                        content=".rail{position:static!important;height:auto!important}"
                    )
                overflow = page.evaluate(
                    "document.documentElement.scrollWidth - document.documentElement.clientWidth"
                )
                if html.stem != "index" and overflow > 0:
                    problems.append(f"{html.name}@{width}: horizontal overflow {overflow}px")
                if (
                    html.stem == "index"
                    and width == 1920
                    and not (OUT / "ask-explore-1920.png").exists()
                ):
                    continue
                if width <= 767:  # fixed bottom tab bar must land at the end of the full page
                    height = page.evaluate("document.documentElement.scrollHeight")
                    page.set_viewport_size({"width": w, "height": int(height)})
                page.screenshot(path=str(OUT / f"{html.stem}-{width}.png"), full_page=True)
                if width <= 767:
                    page.set_viewport_size({"width": w, "height": h})
            ctx.close()
        browser.close()
    for line in problems:
        sys.stderr.write(line + "\n")
    sys.stdout.write(
        f"captured {len(pages)} pages x {len(VIEWPORTS)} viewports; {len(problems)} problems\n"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

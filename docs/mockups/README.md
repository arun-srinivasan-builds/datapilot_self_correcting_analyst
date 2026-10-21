# M2 UI mockups (design only)

Static, high-fidelity mockups for review. **Not the Streamlit implementation**; no shell/theme/Livewire code exists yet. Numbers come from `fixtures/sales_sample.csv` (pandas); agent text is illustrative copy of what real events will carry.

## How to preview

| What | How |
|---|---|
| Gallery of all screens (PNG) | open `docs/mockups/index.html` in a browser |
| Single screen, live, resizable | open any `*.html` (e.g. `ask-explore.html`) and resize the window to see responsive behaviour |
| Screenshots | `docs/mockups/png/<page>-1920.png` and `<page>-390.png` |
| Rebuild | `.venv\Scripts\python docs/mockups/build.py` then `docs/mockups/capture.py` (Playwright + Edge) |

## Light theme (current proposal)

The dark set in this folder is the original iteration and is **not approved**. The premium light redesign lives in `review-light/` (`DataPilot_UI_Review_Light.pdf`, `DataPilot_UI_Review_Light.html`, `gallery.html`, `pages/`, `png/`).

## Review package (dark, original)

`docs/mockups/review/DataPilot_UI_Review.html` (interactive: viewport tabs per screen, sidebar navigation), `DataPilot_UI_Review.pdf` (57 pages, desktop/laptop/tablet/mobile), and `review/png/<screen>__<viewport>.png`. Rebuild: `review/capture_review.py` then `review/build_review.py`; per-screen check results in `review/checks.json`.

## Screens

| Workspace | File | Notes |
|---|---|---|
| Ask & Explore | `ask-explore.html` | profile strip, source pane, preview + column profile, question composer, suggestions, history |
| Agent Livewire | `livewire-{idle,running,exec-error,repair,reviewer-feedback,approved,limit-reached,fault-injection}.html` | lanes canvas, 12-cell counter, live feed, inspector, run facts, message ledger, separate Human stage |
| Insights Studio | `insights-studio.html` | answer, KPI strip, 3 coordinated charts, narrative + verification trail, table, exports, decision, follow-up |
| Tokens + mapping | `tokens.html` | colours, computed WCAG contrast, type/space/shape, state → `RuntimeEvent` table |

Mobile (<768 px): rail becomes bottom tabs, KPI strip 2-up, lanes go vertical, charts switch to a 1:1 narrow variant, tables scroll inside their own pane.

## Design decisions to approve or change

1. Dark, flat enterprise canvas: midnight navy / graphite / slate + electric teal; 3 px radius; hairlines; no card grid, no shadows.
2. Livewire canvas shows only real events; unused loop-back arcs are faint, active ones animate once per real transfer; Human stage is a separate, dashed "pending" node.
3. `TEST FAULT INJECTED` is a persistent amber badge (toolbar + Coder node), visually distinct from natural errors.
4. A **message ledger** lists exactly the counted messages (n of 12); task message and events are not counted.
5. Cost always reads **Pricing not configured** until prices are supplied.
6. Insights Studio leads with the answer, then KPI strip, then charts; approval is a separate bar below the evidence.
7. Currency shown as ₹ because the sample prices are INR-like; this is cosmetic copy, not a product assumption.

## Known limitations of the mockups

- Static HTML: Streamlit's widget DOM will not match pixel-for-pixel; the implementation will use custom CSS + components and be compared against these PNGs.
- Animations are described in CSS but only visible in the live HTML; `prefers-reduced-motion` disables them.
- Plotly interactivity (hover, cross-filter) is not represented.
- Only the dark theme is designed.

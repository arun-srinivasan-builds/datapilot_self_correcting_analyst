# Enterprise BI-Style UI Skill

> Power BI is the **inspiration** (density, hierarchy, coordinated visuals). Streamlit is the framework, not the look. No Power BI branding/assets.

## Anti-patterns (rejected in review)
Grid of identical rounded cards · stacked `st.container()` sections · chat bubbles with charts underneath · default sidebar of disconnected widgets · SaaS hero/landing · decorative charts with no question behind them · emoji-heavy chrome.

## Visual system (tokens in one CSS module)

| Token | Value (starting point) |
|---|---|
| `--bg` | `#0B1426` midnight navy |
| `--surface` | `#121C30` graphite; `--surface-2` `#1A2640` slate |
| `--line` | `#26324A` hairline (1px, used sparingly) |
| `--accent` | `#19C3B1` electric teal; `--accent-2` `#3B82F6` blue |
| `--text` | `#F4F1E8` ivory; `--muted` `#9AA7BD` |
| `--danger` / `--warn` / `--ok` | `#F0556A` / `#F5B84B` / `#3DD68C` |
| Radius | 2–4px max |
| Type | system UI / Segoe UI stack; tabular numerals for KPIs |

Verify AA contrast (≥4.5:1 body, ≥3:1 large/graphics). Colour is never the only carrier of status (add icon/label).

## Composition

- **Report canvas**, not cards: a single surface with a title band, a KPI strip (compact, separated by hairlines, no boxes), then a coordinated visual grid that shares one filter context.
- Hierarchy: the *answer* first (largest), then evidence (charts), then detail (tables), then provenance (code, events).
- Density: small multiples, compact tables, 12–13px secondary text; no oversized empty space.
- Controls: slicer-like filter bar (compact chips/selects), top-bar workspace navigation.
- Interactions: cross-filtering where data supports it (click category → region breakdown updates), drill-down from KPI → table.
- Verification status is a first-class element (Reviewer: Approved / Unapproved / Incomplete; Human: Pending / Approved).

## Workspace specifics
1. **Ask & Explore** — drop zone with format hints, sheet picker, profile summary (rows, columns, nulls, date columns), preview table, quality flags, composer with 3–5 suggested questions derived from the profile.
2. **Agent Livewire** — see `skills/LIVEWIRE.md`.
3. **Insights Studio** — KPI strip → narrative → coordinated Plotly visuals (from `results.json`) → tables → artifacts (py/PNG/PDF) → approval → follow-up.

## Responsiveness
Breakpoints: ≥1400, 1024–1399, 768–1023, <768. At narrow widths: KPI strip wraps to 2 columns, visual grid becomes single column, tables scroll within their own container (never the page), canvas switches to vertical lane layout. Test at 1920/1366/820/390.

## Accessibility
Semantic landmarks, focus-visible styles, keyboard reachability for approval controls, `aria-live="polite"` for event feed, `prefers-reduced-motion` disables pulses/flows, alt text/titles on SVG.

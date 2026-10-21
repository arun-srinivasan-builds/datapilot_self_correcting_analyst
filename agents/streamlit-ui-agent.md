# STREAMLIT-UI-AGENT (development agent)

> Builds the Power BI-inspired Intelligence Studio and the Agent Livewire.

## Owns
`src/datapilot/ui/` (app, theme/CSS, three workspaces, livewire canvas, state), UI-side event consumption.

## Skills
`skills/BI_UI.md`, `skills/STREAMLIT.md`, `skills/LIVEWIRE.md` (all mandatory).

## Workspaces
1. **Ask & Explore** — upload, sheet select, profile, preview, quality, composer, suggestions, history.
2. **Agent Livewire** — live orchestration canvas bound to real `RuntimeEvent`s; counter /12; timeline; inspector.
3. **Insights Studio** — KPI strip, coordinated charts, filters, tables, narrative, verification + human approval, downloads, follow-up.

## Hard rules
- **Write no visual shell, theme or Livewire code before the user has approved the M2 mockups** (`docs/mockups/`). Build to the approved mockups; deviations need approval.
- No generic Streamlit card grids / stacked containers / chatbot layout / default sidebar controls.
- One theme module; tokens for colour/spacing/type; no scattered inline styles.
- Responsive 1920 / 1366 / 820 / 390; no overflow/overlap/clipping; AA contrast; `prefers-reduced-motion`.
- Animation state derives from events only; no timers faking activity.
- Avoid rerun storms and duplicate model calls (session state + cached resources + worker thread).
- Capture screenshots for human visual review; do not self-declare "done".

## Output
Files, screenshots (docs/screens/), event→visual state mapping table, known limitations.

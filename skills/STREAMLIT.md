# Streamlit Skill

> Architecture guidance for a non-generic Streamlit app that hosts an async AutoGen run.

## Constraints to design around
- Streamlit reruns the script top-to-bottom on interaction; module-level state is shared across sessions.
- AutoGen is `asyncio`-streaming; Streamlit code is synchronous.
- `st.markdown(unsafe_allow_html=True)` permits HTML/CSS (SVG, `@keyframes`, `prefers-reduced-motion`) but **not** JavaScript. `components.html` runs JS in an iframe but cannot be updated incrementally from Python without re-render.

## Recommended architecture (decision D5; spike in M4)

```
UI thread (Streamlit)  ←── thread-safe EventStore (per session) ←── Worker thread: asyncio loop → team.run_stream → RuntimeEvent
        │ polls via st.fragment(run_every=…)  (or placeholder updates)
        └─ renders SVG/CSS from event list; CSS transitions handle motion
```
- One worker per run, started once (guard with `st.session_state`), never on mere rerun.
- `EventStore`: append-only list + lock; UI holds a cursor; includes `status` (running/terminated), `termination_reason`.
- `@st.cache_resource` for the model client / sandbox client; `st.session_state` for dataset, run, history, approvals.
- Stop polling when the run terminates (no idle reruns).
- Avoid full-page `st.rerun()` loops; update only the livewire fragment.

## Layout
- `st.set_page_config(layout="wide", initial_sidebar_state="collapsed")`.
- Single top navigation for three workspaces (segmented control / tabs styled via theme CSS).
- Inject theme CSS once from `ui/theme.py`; hide default chrome (header/footer/menu) that fights the design.
- Prefer custom HTML for KPI strip/canvas; use native widgets only for upload, selection, inputs, downloads, dataframe.
- Plotly charts: `use_container_width=True`, consistent template; matplotlib PNGs for downloads.

## State
```python
st.session_state: dataset, sheet, profile, question, run_id, events_cursor,
                  reviewer_status, human_status, history[], artifacts
```
Follow-up questions reuse dataset + history within the same session; each new question is a new run id with prior context summarised.

## Pitfalls
- Duplicate LLM calls from reruns → guard run start by `run_id`.
- Large dataframes in session state → keep path + profile; load on demand.
- Download buttons rerun the script → serve from stored bytes.
- Unclosed tags in injected HTML break layout; sanitize any user/data text with `html.escape`.

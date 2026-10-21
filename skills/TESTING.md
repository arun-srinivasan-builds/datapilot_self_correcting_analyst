# Testing Skill

> pytest + Ruff. Deterministic suite uses a **scripted model client**; live tests are separate.

## Layers

| Layer | Marker | LLM | What it proves |
|---|---|---|---|
| Unit | (default) | none/scripted | ingestion, profiling, termination logic, event mapping, reducers |
| Orchestration | (default) | **scripted client** | routing, repair loop, Reviewer-only approval, 12-cap |
| Sandbox | `sandbox` | none | isolation + limits (needs Docker) |
| Artifacts | (default) | none | PNG labels/units, `analysis.py` rerun identical, PDF 1 page |
| UI | `ui` | none | viewports, overflow, reduced motion, screenshots |
| Live | `live` | real model | genuine autonomous correction end-to-end |

`pytest -m "not live"` is the default CI/gate command.

## Scripted model client (orchestration tests)
A deterministic fake implementing the model-client interface returns a queue of canned responses per agent. Example script: Planner plan → Coder code with `KeyError` → (real Executor/sandbox runs it, produces the real error) → Coder fixed code → Executor OK → Reviewer "chart 2 lacks axis labels" → Coder fix → Executor OK → Reviewer `APPROVED`.
The *error and execution are real*; only the language model is scripted. This validates routing and termination, **not** model intelligence — the live test covers that.

## Required cases (map to `INITIAL.md §13`/§17)
- CSV, XLSX, multi-sheet, missing values, date detection, invalid file, oversize file
- Planner output contains calculations/groupings/charts
- Executor error → Coder receives actual stderr (assert text present in Coder input)
- Reviewer feedback → Coder revision → re-execution
- `APPROVED` from non-Reviewer / inside code / in stdout does **not** terminate
- Reviewer `APPROVED` after failed execution is rejected
- Never exceeds 12 messages across retries; unapproved outcome flagged
- Human approve/reject; follow-up in same session keeps dataset/history
- Numeric accuracy vs pandas ground truth on fixture (PDF-shaped, 12,480 rows) and a second schema
- Every PNG has title, axis labels, units (static check of figure metadata emitted in `results.json`)
- Rerun `analysis.py` twice → identical `results.json` hash
- PDF: ReportLab output has exactly 1 page and contains answer + chart
- Event→Livewire reducer states
- API efficiency: LLM call count ≤ budget for a standard run; no calls on rerun

## Live tests (two separate demonstrations)
- **Demo A — normal run:** no injection; assert the run completes or reports UNAPPROVED honestly; claim self-correction only if a natural error occurred.
- **Demo B — fault injection (test-only, labelled):** mutate the Coder's first output before it enters the conversation; the real Coder must repair from the real stderr. Assert ≥1 `exec_error`, a following Coder message that differs, a subsequent `exec_result ok`, final Reviewer `APPROVED`, ≤12 messages, no human input, and a `test_fault_injected` event + manifest flag.
Never present Demo B faults as natural. Evidence in `docs/evidence/m3/{normal-run,fault-injection}/`.

## UI tests
Playwright at 1920×1080, 1366×768, 820×1180, 390×844: `document.documentElement.scrollWidth <= innerWidth`, no clipped text (bounding-box checks on key elements), screenshots to `docs/screens/` for human review.

## Ruff
```toml
[tool.ruff]
target-version = "py311"
line-length = 100
[tool.ruff.lint]
select = ["E","F","I","B","UP","S","T20"]   # T20 forbids print
```

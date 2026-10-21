# Milestone Log

Active development time only (exclude personal breaks). Times are local (IST). Rework = a repeat cycle caused by a failed gate or review rejection.

| # | Milestone | Started | Ended | Active time | Rework cycles | Status |
|---|---|---|---|---|---|---|
| M1 | Requirements & template adaptation | 2026-10-15 ~17:20 (PDF read 17:30) | 2026-10-15 (approved for PRP generation) | — | 1 (user-requested cleanup/validation) | **Approved** (D3 = L3) |
| PRP | PRP generation (`PRPs/datapilot-prp.md`) | 2026-10-15 | 2026-10-15 (v1.1 corrections applied) | — | 1 (review corrections: message counting, model check to M2, demos, feasibility, mockup gate) | **Approved (v1.1)** — M2 executed against it; amendments proposed in `docs/M3_READINESS_PLAN.md` (C2, C3) are NOT yet approved |
| M2 | Foundation & premium UI shell | 2026-10-15 | 2026-10-15 (closed 2026-10-16) | — | 3 (model-check script classification; wider viewport checks; design-direction change to light theme) | **COMPLETED — APPROVED (2026-10-16)** |
| M3 | Real AutoGen execution engine | 2026-10-16 | | | 0 | **Stages 0-6 accepted. Stage 7 (follow-ups + human approval) implemented — awaiting review (Stage 8 NOT authorized)** |
| M4 | Live Agent Livewire | | | | | Not started |
| M5 | Insights & stretch goals | | | | | Not started |
| M6 | Quality & validation | | | | | Not started |
| M7 | Docker, VPS & closure | | | | | Not started |

## M2 detail

| Step | Result | Evidence |
|---|---|---|
| 0 Model check `gpt-6-luna` | **PASS** (availability, completion, seed, AutoGen client). `max_tokens` and `temperature=0` unsupported (informational) | `docs/evidence/m2/model-check.md` |
| 1 Config/pins | Python 3.11.9 venv; pins in `pyproject.toml`, `requirements*.txt`; Ruff + pytest markers; AutoGen maintenance-mode risk | `docs/RISKS.md` |
| 2 Fixtures | 12,480-row sample, alt schema (3,210 rows incl. 10 dups, nulls), 3-sheet xlsx, truth JSON; reproducible | `fixtures/` |
| 3 Ingestion | CSV/XLSX, sheets, validation (magic bytes, size, zip-bomb, macros, dup columns, caps), profiling | `tests/ingestion/` |
| 4 Events | immutable `RuntimeEvent`, thread-safe `EventStore`, pure reducer (counter, terminal exclusivity, Reviewer-only approval, human separate) | `tests/events/` |
| 4b Usage | token tracker, price table; "Pricing not configured" when unset | `tests/agents/` |
| 5 Mockups | 12 pages x (1920, 390), tokens, state→event map | `docs/mockups/` |
| 5b Review package | HTML + PDF (57 pages) + 44 screenshots at 1920/1366/820/390; automated checks 0 findings after fixes | `docs/mockups/review/` |
| 5c Light-theme rework | **Dark mockups NOT approved**; premium light identity requested. Full light package built beside (not over) the dark set | `docs/mockups/review-light/` |
| 6 Approval gate | **PASSED 2026-10-15** — light theme APPROVED (`docs/mockups/review-light/DataPilot_UI_Review_Light.pdf`) | this file |
| 7 Streamlit visual implementation | **DONE 2026-10-15** — three workspaces, light theme, event-driven Livewire (design-preview only until M3) | `src/datapilot/ui/`, `docs/screens/m2/` |

## Rework notes
- **M2 step 0 (2026-10-15):** first `scripts/check_model.py` run reported overall FAIL because informational parameter probes (`max_tokens`, `temperature=0`) were classified as required checks. The model itself was available and AutoGen-compatible. Fix: probes are `required=False` and reported as "UNSUPPORTED (informational)"; check re-run once (2 extra small live calls). Rework cycle 1.
- **M2 mockups (2026-10-15):** self-review of renders found and fixed: arc/label overlap in Livewire, chart label collision, oversized chart text, running-state counter inconsistent with messages, illegible mobile charts, mobile tab-bar capture artefact, composer order on mobile. These are internal visual iterations before user review.
- **M2 review package (2026-10-15):** user requested a consolidated visual review before approval. Extending checks from 2 to 4 viewports found real defects, all fixed without changing the approved concept: toolbar overflowed at 820 px (now wraps; mock flag hidden <1100 px); horizontal Livewire lanes rendered ~8 px text at tablet width (vertical lanes now used below 1024 px); repair/feedback labels were crossed by arcs in the vertical lanes (arcs nested, labels painted last with halo, rotated into the free corridor); mobile ledger outcome text was clipped (now wraps). Final automated result: 11 screens x 4 viewports, 0 overflow / clipping / label-overlap / contrast findings. Aesthetic judgement remains with the reviewer. Review-preparation counted as rework cycle 2 for M2 (defects found by wider checks, not by user rejection).

## Design-direction change (2026-10-15): premium light theme
- **Decision (user):** the dark-theme mockups are not approved for implementation. Information architecture, workspaces, event-driven Livewire concepts and layout are kept; the visual identity becomes a premium LIGHT enterprise analytics theme (ivory canvas, white surfaces, slate type, deep-teal action; restrained gold / green / coral for states).
- **Preserved:** the dark iteration remains untouched as the original design iteration (`docs/mockups/*.html`, `docs/mockups/review/`).
- **New package:** `docs/mockups/review-light/` — `DataPilot_UI_Review_Light.pdf` (58 pp), `DataPilot_UI_Review_Light.html` (interactive), `gallery.html`, `pages/*.html` (live), `png/` (44 screenshots at 1920/1366/820/390), `checks.json`, `qa_extra.json`.
- **Palette adjustments for WCAG:** accent #087F8C → #077A86 (AA on ivory), gold #C49545 → #B58429 for graphics (#C49545 kept as decorative `--gold-soft`), success #21866B → #1F7F63, coral #C7515C kept for graphics with darker `--danger-ink` #A8323F for text.
- **Layout refinements:** numbered Ask & Explore steps with a completeness/quality profile table; Livewire gains a node-state legend, explicit WAITING / AFTER REVIEW states and a compact ledger; Insights Studio uses a report-style serif answer band, a contribution column with total row, a 2-column narrative with verification trail and compact exports.
- **QA defects found and fixed during rework:** active mobile tab label contrast 4.37:1; SVG accent-bar class collision; chart labels rendering at ~8 px on laptop/tablet (added per-breakpoint chart variants; smallest label now 11.9 px); node status text enlarged to 11 px and verified to fit inside nodes; mobile segmented control and nav targets enlarged; stray markup in the exports pane; stale "amber/red" wording in the state map.
- **Result:** overflow / clipping / label-overlap / contrast: 0 findings (11 screens × 4 viewports); chart-label size, responsive navigation and mobile usability: 0 findings. Aesthetic judgement remains with the reviewer.
- **Not done (by instruction):** no Streamlit shell, theme or Livewire code; no M3; no deploy; no commit.

## Approval record (2026-10-15)
- Light-theme visual design: **APPROVED** by the user (written), based on `docs/mockups/review-light/DataPilot_UI_Review_Light.pdf`.
- Dark-theme mockups (`docs/mockups/*.html`, `docs/mockups/review/`): **superseded**, retained for history.
- M2 visual implementation (Streamlit shell, theme, workspaces, Livewire render from events): **authorized**.
- **M3 (real AutoGen orchestration): NOT yet authorized.** No deploy, no VPS change, no commit.
- Boundary: until M3 the app may show only real ingestion/profile data plus clearly labelled **design-preview** (scripted) states; nothing is presented as live AI execution.

## M2 UI implementation (2026-10-15)
**Implemented:** `src/datapilot/ui/` — `app.py` (entry), `chrome.py` (theme injection, rail, toolbar chips), `state.py` (session + cached ingestion), `markup.py` (escaped HTML fragments), `charts.py` (SVG charts, per-breakpoint variants), `viewmodel.py` (events → canvas/ledger/feed), `preview.py` (labelled design-preview scenarios + pandas fixture numbers), `workspaces/{explore,livewire,insights}.py`, `static/theme.css`, `.streamlit/config.toml`.
- **Ask & Explore:** real upload (CSV/XLSX, 25 MB cap, validation errors shown), sample datasets, sheet picker, quality profile, 10-row preview, schema-driven suggestions, composer. "Run analysis" is **disabled** (live agents = M3).
- **Agent Livewire:** renders only from `RuntimeEvent`s through the real reducer; idle state is genuine; 7 scripted *design-preview* states selectable and labelled everywhere (banner + toolbar chip); 12-message counter and ledger from the event log; TEST FAULT INJECTED persists; Human stage separate; inspector tabs from events; **no token figures shown**.
- **Insights Studio:** answer-first report, KPI strip, 3 charts, detail table, narrative + verification trail, separate Reviewer/Human status, exports **disabled** (no verified artifact exists), Reject / Approve / follow-up wired to real human events (Approve only enabled for a Reviewer-approved run).
- **Not fabricated:** no AI output, token usage, cost, repairs or results are presented as live; preview numbers are pandas results from `fixtures/sales_sample.csv`, labelled.

**Deviations from the approved mockups (all minor):**
1. Charts are static SVG matching the mockups (Plotly adoption deferred to M5 when `results.json`-driven interactivity exists).
2. Native Streamlit widgets (uploader, selects, segmented controls, buttons) replace the mockups' static controls; styled to the theme but not pixel-identical.
3. Inspector uses a state-aware segmented selector instead of mockup tabs (Streamlit cannot preselect `st.tabs`).
4. Rail/bottom-tab navigation uses native buttons (no page reload) instead of anchors; tooltips come from Streamlit.
5. Livewire pane heights are not forced equal (Streamlit column wrappers); the ledger collapses unused slots as in the light mockups.
6. Sample dataset shows 59 duplicate rows (real, found by ingestion) whereas the mockup showed 0.

**QA defects found in the live app and fixed:** Streamlit's −1rem markdown margin clipped HTML blocks; stdlib `html` module shadowed by a local `html.py` (renamed `markup.py`); rail active state rendered as a solid primary button; missing pane gaps; unbalanced HTML across `st.markdown` calls; clipped tab labels; stale CSS cache; Material icon glyph box 16 px vs 22 px; decision bar overflow at 390 px; segmented-control targets 30 px; the checker itself was blind to clipping inside Streamlit's scroll container (fixed, re-run).
**Reducer fix (found by the UI):** a chat message from the Executor/Reviewer no longer overwrites that node's real result status (`error`/`ok`/`feedback`/`approved`) — test added.

**Remaining M3 dependencies:** real AutoGen team + `T-TERM-*`; sandbox executor; live run → EventStore bridge (`st.fragment` polling spike U5); token usage/cost wiring (UsageTracker exists); verified exports (analysis.py/PNG/PDF, M5); follow-ups as new runs; replace design-preview scenarios with real runs (preview stays as a labelled review aid or is removed).

## M2 final acceptance evidence (2026-10-15)
- **Deliverable:** `docs/screens/m2/DataPilot_M2_Actual_UI_Review.pdf` — 34 pages of screenshots of the **actual running Streamlit app** (Edge/Chromium via Playwright): Ask & Explore (loaded), Insights Studio, all eight Livewire states at desktop, and repair / approved / limit-reached / fault-injection at laptop, tablet and mobile. Every non-idle Livewire page and the Insights page carries a "DESIGN PREVIEW · NON-LIVE" badge. Builder: `docs/screens/m2/build_review.py`; raw screenshots: 44 PNGs (11 pages × 4 viewports) in the same folder.
- **Coverage gap closed:** the browser walkthrough previously skipped *running* and *execution error*; it now covers idle + all seven preview states. New `tests/ui/test_acceptance_states.py` (29 tests) asserts per state: node labels, run chip, counter, banner, lanes text.
- **Rules verified by tests:** Reviewer approval never implies human approval (human stays `none` until an explicit decision); a limit-reached run cannot be human-approved, even with forged session state (guard added in `preview.events_for`, UI button disabled, lanes show RUN UNAPPROVED); TEST FAULT INJECTED present at every event step after injection and as a persistent chip on all three workspaces (chip moved into the shared toolbar chips); the counter equals counted agent messages only (task message, guardrail, usage and human events never move it); every scripted event is flagged `preview`, and importing the UI loads no `autogen*`/`openai*` module, so no preview can be AutoGen execution.
- **Defects found and fixed during acceptance:** stderr/code blocks rendered on one line (Streamlit's markdown pass collapses raw newlines; Streamlit also replaces `<pre>` with its own component, dropping classes) — now `<div class=codeblock|errblock>` with entity newlines + test; a `div.err` selector would have restyled feed rows (renamed classes).
- **Environment incident:** mid-session the project `.venv` was found re-pointed at Python 3.14 (`pyvenv.cfg` / `python.exe`, cause external to the work: not a command of this session). Restored to Python 3.11.9 with `py -3.11 -m venv .venv` (site-packages intact, `pip check` clean) and the full suite re-run.
- **Results:** `pytest -m "not live and not sandbox"` **121 passed, 0 failed**, coverage **94%**; Ruff clean; browser QA: 4 viewports × 11 pages, 0 overflow / clipping / label overlap / contrast / control-size findings, 0 console errors.
- **Not done (by instruction):** M3, deploy, VPS changes, commit.

## M2 formal closure (2026-10-16)
**Decision (user, 2026-10-16): M2 APPROVED** on the reported technical, functional and responsive-UI acceptance evidence.

| Result | Value |
|---|---|
| Automated tests | **121 passed**, 0 failed (`pytest -m "not live and not sandbox"`) |
| Coverage | **94%** (1,399 statements, 77 missed) |
| Ruff / pip | `ruff check` and `ruff format --check` clean (48 files); `pip check` clean |
| Browser checks | **44** viewport/page checks passed (11 pages x 1920/1366/820/390); 0 overflow / clipping / label overlap / contrast findings; 0 console errors |
| Livewire | all **eight** states covered (idle, running, execution error, repair, reviewer feedback, approved, limit reached, fault-injection) |
| Approvals | Reviewer approval and Human approval remain **separate**; a limit-reached run cannot be human-approved |
| Honesty | no simulated execution presented as live; every preview state is flagged `preview` and labelled "DESIGN PREVIEW · NON-LIVE" |
| UI | premium light theme implemented as approved |

**Re-verified at closure (2026-10-16, this session):** venv interpreter is **Python 3.11.9** (`pyvenv.cfg` home = `Python311`); `pip check` clean; Ruff check + format clean; `121 passed` in 159 s with 94% coverage. Numbers match the reported ones.

**Preserved M2 acceptance evidence (unchanged files, not modified at closure):**
- `docs/screens/m2/DataPilot_M2_Actual_UI_Review.pdf` — 34 pages, actual running Streamlit app (7.06 MB).
- `docs/screens/m2/*.png` — 44 raw screenshots of the actual app; `test-results.json` — recorded results; `build_review.py` — PDF builder.
- `docs/screens/m2/EVIDENCE_MANIFEST.sha256` — SHA-256 of every evidence file (47 entries), created at closure so later changes are detectable. Verify with `sha256sum -c EVIDENCE_MANIFEST.sha256`.
- Also kept: `docs/evidence/m2/model-check.md` (gpt-6-luna), `docs/mockups/review-light/` (approved design), dark set (superseded, history).
- Caveat: these files are **untracked in git** (no commit was requested). They are on disk and not ignored by `.gitignore`; they are not yet in version history.

**Not done (by instruction):** M3 implementation, deploy, VPS inspection/changes, host container-service install/changes, commit.

## M3 architecture approval (2026-10-16)
Basis: `docs/M3_READINESS_PLAN.md`. Approved by the user in writing with the conditions below.

| ID | Decision | Status |
|---|---|---|
| C1 | Guarded `SelectorGroupChat` is the production path; RoundRobin is a labelled test baseline | **Approved** |
| C2 | External wall-clock watchdog with reliable container termination + forced cleanup; verify runtime-specific timeout capabilities instead of assuming identical Docker/Podman flags | **Approved** (PRP §6.2 amended; implementation in Stage 4) |
| C3 | Stdlib broker, JSON control messages, raw dataset `PUT` by SHA-256; request-size limits, digest verification, strict validation, safe staging | **Approved** (Stage 4) |
| C4 | Loopback-only HTTP broker + bearer auth for Windows dev; Unix-domain socket kept as the *proposed* VPS design; never public; no app secrets or Docker socket into execution containers | **Approved** (Stage 4; UDS remains a proposal) |
| C5 | Unverified function-calling / structured-output capabilities declared `False`; **no live capability probe authorized** | **Approved — implemented** (`agents/client.py`, test) |
| C6 | Configurable `MAX_RUN_TOKENS` with explicit safe default, clear reporting; independent 12-message cap and wall-clock kept | **Approved — implemented** (default 200,000; `RUN_TIMEOUT_SECONDS` default 300; both in `.env.example`) |
| C7 | Minimal real-event streaming in M3; M4 keeps animation, replay, polish | **Approved** (Stage 8, not yet started) |
| C8 | Labelled design-preview scenarios kept temporarily; preview and live strictly separated | **Approved** (no change yet; separation test added) |

Conditions: Python 3.11.9 mandatory, interpreter guard first, no automatic venv recreation/repair; Docker Desktop may be started and a pinned dev image built **only when Stage 4 is authorized**; no Podman install; no VPS inspection/changes; no Traefik/deploy changes; **live model calls need approval before Stage 9**.
Authorization given: **Stages 0-3 only.** Open: confirm `MAX_RUN_TOKENS=200000` as the safe default; add the two new keys to the CLAUDE.md env list (not edited: it is a protected project-rules file).

## M3 Stages 0-3 (2026-10-16)
| Stage | Result |
|---|---|
| 0 Preflight | `src/datapilot/env_integrity.py`, `scripts/check_env.py`, `tests/test_env_integrity.py` (8 tests), pytest session-start fail-fast (`tests/conftest.py`), Streamlit start-up banner, baseline `docs/evidence/m3/env-baseline.json`. Checks: interpreter 3.11, venv == project `.venv`, `pyvenv.cfg` 3.11, exact pins, no legacy AutoGen dists, `pip check`. Report-only: never repairs |
| 1 Contract spikes | `docs/evidence/m3/contracts.md`; findings pinned in `tests/agents/test_autogen_contracts.py` (offline, no live calls) |
| 2 Termination/routing | `agents/termination.py` (`RunState`, `RunTerminator`, `RunOutcome`), `agents/routing.py` (`GuardedSelector`), T-TERM-1..5 + all PRP §3.3 table rows green |
| 3 Participants/events | `agents/{prompts,participants,teams,runner,executor,codeblocks}.py`, `events/mapping.py`, `sandbox/contracts.py`; scripted orchestration through real AutoGen teams |
| Gate | Ruff + format clean; `pip check` clean; `218 passed` (was 121), coverage **95%**; no live OpenAI calls; no container runtime used |

**Defects found and fixed during the stages:** `execute_code_blocks` must name its parameter `cancellation_token` (library calls by keyword); a run timeout/stop waited 30 s for the in-flight execution (token now linked to the backend call; ~1 s); approval fence detection mis-handled a one-line ```` ```x``` ```` fence (now counts all fence markers); an ordering race between executor events and consumer-side message mapping (messages are now mapped inside the team, before the next speaker is chosen). Rework cycles: 0 (no gate or review rejection).

## M3 Stage 4: secure sandbox (2026-10-16)
Authorized: Stage 4 only. Decisions applied: Docker Desktop (already running; nothing installed/upgraded), pinned image pulled + built (base `python@sha256:e88e9763...f6ce`, image id `sha256:354c6f52...e028d638`, deps pinned = app pins), `MAX_RUN_TOKENS` default **30000** (enforced, see report), CLAUDE.md env block updated (keys only; rules untouched). No live OpenAI call, no VPS access, no Podman, no deploy, no commit.

| Item | Result |
|---|---|
| Built | `sandbox_service/{image,broker}` (stdlib loopback broker, bearer auth, fixed docker argv, watchdog, cancellation, reaper, retention), `src/datapilot/sandbox/{client,backend}.py`, `src/datapilot/agents/budget.py` |
| Sandbox suite (real containers) | **84 tests, all passed** (`-m sandbox`), repeated runs stable except one unexplained 12-minute engine stall seen once (open risk, now logged) |
| Full regression (`-m "not live"`, includes sandbox) | **306 passed**, 0 failed; coverage **93%** over `src/datapilot` + `sandbox_service` (was 218 tests / 95% for src only before Stage 4; broker `__main__` is exercised only as a subprocess so reads 0% in-process) |
| Gate | env guard green (3.11.9), Ruff check + format clean, `pip check` clean |
| Cleanup | 0 labelled containers, `.sandbox/` empty after the full run |
| Isolation level | per-execution container behind a broker, Docker runtime: **NOT security-equivalent to the proposed rootless Podman VPS design**; VPS feasibility UNKNOWN. Details and limitations: `docs/evidence/m3/sandbox-report.md` |

Defects found and fixed by the suite: reaper race -> 500; leaked artifact directories (empty/cancelled runs); connection reset on early errors with unread bodies; unexpired datasets + fixture teardown on read-only files.
Rework cycles this stage: 0 gate rejections (6 internal test-fix iterations).

## M3 Stage 5: real sandbox integration (2026-10-16)
Authorized: Stage 5 only; scripted model replies, **no live OpenAI call**, no VPS/Podman/deploy/commit, no UI design change, no Stage 6. Preflight green (3.11.9 guard, engine + pinned image, broker subprocess health/auth). `.env` had no `SANDBOX_TOKEN`: a random local one was appended to the gitignored `.env` (not printed).

| Item | Result |
|---|---|
| Delivered | `reports/results.py` (minimal results.json contract) enforced in `ObservedCodeExecutor`; call-level `usage` events + per-source usage; reserved per-call ceiling; `LatestCoderExecutorAgent`; broker CLI bounds + per-phase timing; `scripts/sandbox_soak.py`; `tests/integration` (19 scenarios), `tests/reports` (15) |
| Integration scenarios | repair, reviewer feedback, round-robin baseline, OOM repair, endless OOM (limit), exec timeout repair, run timeout, user stop, invalid/multiple blocks, results.json missing/NaN, approval-while-invalid, hostile dataset, usage reconciliation, selector-fallback usage, independent token/message budgets, ceiling reservation, no-fabrication proof — all passed with real containers |
| Defect found | AutoGen's executor agent bundled stale blocks from earlier unusable Coder replies with the next valid script (spurious rejection); fixed by executing only the latest Coder message |
| Regression | **342 passed**, 0 failed; coverage **93%** (`src/datapilot` + `sandbox_service`); Ruff + format + `pip check` + 3.11 guard green; cleanup: 0 managed containers, `.sandbox/` empty |
| Docker stall | **still OPEN**: 40-run soak with a 300 s idle gap showed no outlier (max 4.9 s); a second unexplained >120 s stall occurred once on the first scenario run of this stage; calls are now bounded (30 s) and stall-tolerant, per-phase timings added; cause not established |
| Evidence | `docs/evidence/m3/stage5-integration.md`, `docs/evidence/m3/stage5/` |

## M3 Stage 6: controlled fault injection (2026-10-16)
Authorized: Stage 6 only; scripted replies, no live OpenAI call, no VPS/Podman/deploy/commit, UI untouched, no Stage 7/8.

| Item | Result |
|---|---|
| Delivered | `datapilot/faults.py` (test-only, gated by `APP_ENV=test|diagnostic` + `FAULT_INJECTION`), `FaultInjectingCoder` (rewrites the Coder's own memory to match the injected code, verified), injected-code flags on events, `tests/integration/test_stage6_fault_injection.py` (29), no-Docker memory test |
| Scenarios (real containers) | injected error -> repair; disabled/normal; production refusal; unusable-reply skip; non-applicable fault (explicit ERROR); 5 failures to the 12-message limit; round-robin approval blocked then valid; token budget and message cap; hang -> sandbox timeout repair / run timeout / user stop; injected vs natural distinction (events + Livewire view-model); natural OOM not mislabelled |
| Regression | **372 passed**, 0 failed; coverage **94%**; 3.11 guard, Ruff, `pip check` green; cleanup: 0 managed containers, `.sandbox/` empty |
| Kept OPEN | Docker stall (4th observation: one Stage 5 test took 130 s in an earlier full run; not reproduced in an 18-run loop or the final full run; stack-dump instrument now armed at 45 s); `BudgetedClient` streaming coverage (78%); real network cancellation (unverified until live) |
| Evidence | `docs/evidence/m3/stage6-fault-injection.md`, `docs/evidence/m3/stage6/` |

## M3 Stage 7: follow-ups and human approval (2026-10-16)
Authorized: Stage 7 only; scripted replies, no live OpenAI call, no VPS/Podman/deploy/commit, UI unchanged, no Stage 8.

| Item | Result |
|---|---|
| Delivered | `datapilot/session.py` (`Session`, `RunRecord`, `DatasetRef`, `Actor`, human `approve`/`reject`, audit log); every question = new run_id/EventStore/team/RunState (fresh 12-message cap, token budget, wall clock); context = sanitized Reviewer-verified facts + artifact identities only; approval needs Reviewer approval, no earlier decision, the run's own artifact digest and artifacts still intact in the broker; reducer hardening for human decisions; `exec_id`/`results_sha256` in exec events; `run_to_report` |
| Tests | 17 real-container scenarios, 8 session unit tests, 3 reducer tests — all passed |
| Regression | **400 passed**, 0 failed, 18 min; coverage **94%**; 3.11 guard, Ruff, `pip check` green; cleanup: 0 managed containers, `.sandbox/` empty |
| Docker stall | **Explained**: the laptop's Windows Modern Standby freezes the test process and Docker's VM (e.g. a pure-Python test measured 2,213.7 s; log shows standby 19:10:53→19:47:48 = 2,214 s; earlier stalls match standby durations). Mitigation in tests: process-scoped keep-awake incl. display-required (screen stays on during the suite; opt-out `DATAPILOT_NO_KEEP_AWAKE=1`) + resume-tolerant engine fixture. Proposed to close; decision left to the user |
| Still open | `BudgetedClient` streaming coverage (78%); real network cancellation; reasoning-token accounting; Docker Desktop ≠ rootless Podman VPS; fault injection uses a private AutoGen attribute |
| Evidence | `docs/evidence/m3/stage7-followups-approval.md`, `docs/evidence/m3/stage7/` |

## M3 Stage 9 + live UI + M5/M6 slice (2026-10-21, one session)
Authorized by the user: live `gpt-6-luna` calls (existing `.env` key), run through M6; M7 (VPS/deploy) NOT started. No commit, no VPS access, no Podman.

| Item | Result |
|---|---|
| Docker | Docker Desktop was stopped; started it (previously approved for this project), image `datapilot-sandbox:m3` present |
| Demo A (normal run) | `docs/evidence/m3/normal-run/`: Reviewer APPROVED at message 4/12, 1 execution, ~10.4k tokens. Answer Electronics / South matches ground truth; the Coder removed the 59 flagged duplicate rows, so the amounts differ slightly from the truth file (see finding F1) |
| Demo B (fault injection) | `docs/evidence/m3/fault-injection/`: test-only fault `bad_column_lookup` (new; the earlier `missing_column` fault did not apply because the real Coder finds columns through a helper, and the harness refused to silently no-op). Real `KeyError` in the container -> stderr returned verbatim to the Coder -> v2 repaired -> Reviewer APPROVED at 6/12, 2 executions. Numbers match ground truth exactly (-3,980,399.85; -5,596,984.50). First attempt kept in `fault-injection-attempt1-token-limit/` (repair worked, but the 30k token budget ended the run before review) |
| Live UI | `ui/live.py` (event-loop thread + broker bootstrap + `LiveSession`), Run button enabled, Livewire polls the real `EventStore` with `st.fragment(run_every=1)` and stops itself, Stop button, real token table, terminal-reason texts (limit / token budget / timeout / stopped / error). Verified in the browser: run, Livewire, Insights, human Approve, same-session follow-up (new run, counter back to 1/12, prior verified facts in context) |
| Insights Studio (live) | Facts/KPIs/charts straight from `results.json` + PNG artifacts, verification trail from events, `analysis.py` / PNG / 1-page PDF exports (Reviewer-approved runs only), human approve/reject, follow-up, reproducibility button |
| PDF | `reports/pdf.py` (ReportLab, always one page, hostile text escaped), 3 tests |
| Reproducibility | `reports/repro.py`: exported script re-run in a fresh container, answer facts compared; 4 unit tests + live test (passed) |
| Live eval suite | `tests/live` (`pytest -m live tests/live`): ground-truth accuracy, alternate schema, multi-sheet Excel (selected sheet), prompt injection in cells, reproducibility. **5 / 5 passed**. Evidence in `docs/evidence/m5-m6/live/` |
| Logging | AutoGen INFO events (full prompts incl. dataset samples) are now silenced in app logs |
| Config | `MAX_RUN_TOKENS` 30000 is too small for a repair + review round (`.env` unchanged; demo B and live suite use 80000 via environment) |

**Findings**
- F1: the sample dataset has 59 flagged duplicate rows. Agents may or may not remove them, which moves the amounts (~4%) but not the category/region answer. Live evals therefore assert categorical answers exactly and do not pin amounts.
- F2: a 30,000-token run budget cannot cover a repair plus a review round with this model (reasoning tokens count). Recommend 80,000 as the default; needs the user's decision before changing `.env.example`.
- F3: with the Streamlit app, `LiveSession` is held in `st.session_state` and the broker subprocess is started on demand from the app; both survive reruns but not a server restart.

**Gate (2026-10-21):** `pytest -m "not live"`: 405 passed + 2 architecture-boundary tests rewritten and re-run green (the UI boundary moved: only `ui/live.py` may import agent/sandbox code, and no UI source may reference fault injection); coverage 88% over `src/datapilot` + `sandbox_service`; `pytest -m live tests/live`: 5/5; Ruff check + format and `pip check` clean. Not done: M7 (VPS inspection, Docker app image, Traefik, deploy), formal REVIEW-AGENT report, user visual sign-off, accessibility audit, a re-run of the whole suite after the last lint-only edits.

## Public demo redesign (2026-10-21)
Request: the non-admin page must be easy for anyone to understand, look premium, say clearly what to check, show an animated workflow and premium charts; the admin page must not change.

| Item | Result |
|---|---|
| Page | `DATAPILOT_MODE=demo` now renders one guided page (`ui/demo_page.py`, `static/demo.css`): plain-English hero, 4 numbered steps (question, watch the team, answer, why trust it), recording picker (Run A smooth, Run B watch a mistake get fixed), answer card, key figures, charts, trust checklist ("what to check and how"), downloads (analysis.py, one-page PDF, PNG) |
| Animated workflow | `ui/demo_flow.py` (self-contained HTML/JS iframe): four agents, a packet moving between them, red dashed loop-back on crash/feedback, real elapsed time per step, play/pause/back/next/speed/scrubber, auto-starts when scrolled into view, step list, 2x2 layout on phones, reduced-motion respected. Frames come only from real events (`ui/demo_frames.py`); text is set via textContent and JSON is escaped |
| Premium charts | `ui/demo_charts.py`: native Plotly (rounded bars, diverging red/teal with the biggest fall highlighted, compact labels, hover values, one-line takeaway). Needs series data, so the results contract gained optional `charts[i].data` (categories + series, validated, 12 new tests) and the Coder/Reviewer prompts ask for it |
| Re-recorded demo runs | Both runs re-recorded live with the new prompt: Run A approved at 4/12 (1 execution), Run B real KeyError -> repair -> approved at 6/12 (2 executions). Old evidence stays in git history |
| Admin unchanged | The demo conditionals added earlier to the admin workspaces were removed again; diff of admin files vs the pre-demo commit is only a "TEST FAULT INJECTED" chip (shown only if a fault event exists) and a one-line crash fix. Admin browser tests (4 viewports) pass. Side effect to know: the Coder prompt change applies to live runs too (they now also emit chart data; the admin page ignores it) |
| Tests | 21 new demo tests + 5 browser tests (4 viewports: no overflow, animation reaches the answer, 2 native charts, Run B crash and repair). Offline suite 284 passed; admin browser suite 4 passed; Ruff/format clean |
| Not done | Admin site still shows the agents' flat PNG charts (by request, untouched). Full sandbox/integration suite not re-run after the prompt change (scripted tests do not depend on the prompt text) |

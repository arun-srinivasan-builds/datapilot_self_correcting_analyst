# M3 Readiness Plan — Real AutoGen Execution Engine

> Status: **FOR REVIEW. No M3 code written. No deploy, commit, VPS inspection, or host container-service change.**
> Date: 2026-10-16 · Basis: `PRPs/datapilot-prp.md` v1.1 §3, §5 (M3), §6, §8, §12; `CLAUDE.md`; installed `autogen-agentchat==0.7.5` source (read-only inspection); M2 code.

---

## 1. Verified starting state (checked this session)

| Item | Finding |
|---|---|
| Interpreter | `.venv` = **Python 3.11.9** (`pyvenv.cfg` home `...\Python311`); `pip check` clean |
| Gate | Ruff clean; `121 passed`, coverage 94% (matches the M2 report) |
| AutoGen | `autogen-agentchat/core/ext==0.7.5` (maintenance mode, R-AG1, D10 approved) |
| Model | `gpt-6-luna` PASS in M2 (`max_tokens` and `temperature != 1` rejected; `seed` ok). `function_calling`/`structured_output` **not exercised** |
| Existing M3 inputs | `events/{models,store,reducer}.py`, `agents/{client,usage}.py`, `config.py`, UI viewmodel/Livewire reading `RuntimeEvent`s |
| Not existing yet | `agents/{participants,teams,routing,termination,prompts,human}.py`, `sandbox/`, `sandbox_service/`, `events/mapping.py`, `guardrails/` |
| Container tooling (read-only probe) | Docker CLI 29.7.2 installed; **Docker Desktop engine NOT running** (named pipe absent); WSL distros `Ubuntu`, `docker-desktop` listed; **`podman` not installed** |
| VPS | Not inspected (not authorized) |

## 2. Architectural findings from the installed AutoGen source (change the plan)

| # | Finding (file in `autogen_agentchat`) | Consequence |
|---|---|---|
| A1 | `CodeExecutorAgent` **without** `model_client` returns only `TextMessage(content=execution_result.output)` — no exit code, no `CodeExecutionEvent`/`CodeGenerationEvent` (`agents/_code_executor_agent.py:531-543`; those events exist only on the `model_client` path) | Exit status and structured stdout/stderr **must come from our `BrokerCodeExecutor` hook**, shared with routing through a per-run `RunState`. Routing must never parse the Executor text for "error". U3 is settled by source; pin it with a test |
| A2 | No code block in the scanned messages → the agent still emits a counted `TextMessage` ("No code blocks found…") | Selector must route Executor → Coder in that case; it consumes budget. Prompt + pre-check must make this rare |
| A3 | `extract_code_blocks_from_messages` concatenates **all** fenced blocks of all scanned `Coder` messages | Enforce exactly one ```python block per Coder message. More than one → synthetic guardrail event + route to Coder, never executed |
| A4 | `MaxMessageTermination` counts `BaseChatMessage` in each delivered batch (`conditions/_terminations.py:86`) | Library counter is not used for the 12 rule (PRP §3.2). App-owned `RunTerminator` is the single counter; the UI reads the same `RunState` (no second counter to drift) |
| A5 | `TaskResult.stop_reason` is `str | None`, the content of the `StopMessage` (`base/_task.py`, `_base_group_chat.py:555`) | `RunOutcome` lives in app state; `stop_reason` is informational only. U4 settled by source; pin with T-TERM-5 |
| A6 | `SelectorGroupChat` always needs a `model_client`; `selector_func` returning `None` falls back to an LLM call; fallback prompt branches on `model_info["family"]` (`_selector_group_chat.py:241`; we declare `"unknown"`) | Selector LLM calls produce **no** agent message but **do** cost tokens → usage must be reconciled against client `total_usage()`, not only message `models_usage`. Use a separate client instance for attribution |
| A7 | `ReplayChatCompletionClient` ships in `autogen_ext.models.replay` | Deterministic orchestration tests need no new dependency and no live calls |
| A8 | Reducer keeps one `run_id` per state (`events/reducer.py:74`) | Follow-ups (new run) need a new reducer state per `run_id`; add test |

## 3. Conflicts and gaps in the approved documents (need a decision)

| # | Issue | Recommendation |
|---|---|---|
| C1 | `CLAUDE.md`: "Executor failure routes to Coder, never silently onward to Reviewer". PRP RoundRobin baseline routes E✗ → **Reviewer** (relay). The PRP itself marks this the weaker baseline | Guarded `SelectorGroupChat` is the **only production path**; RoundRobin is a labelled assignment-baseline/test target, never the default. Please confirm (D4 is "planning assumption") |
| C2 | PRP §6.2 broker flags include `--timeout`, which exists for **Podman only**; `docker run` has no equivalent | Broker wall-clock kill + forced container removal is the normative timeout on every runtime; `--timeout` is an extra Podman layer |
| C3 | PRP §6.2 broker API uses multipart upload. No web framework is allowed (FastAPI forbidden, no new deps); stdlib has no multipart parser | Broker = stdlib `ThreadingHTTPServer`, JSON bodies; dataset sent once as a raw `PUT /v1/datasets/{sha256}` body, runs reference `dataset_id`. Needs a PRP amendment (API shape only) |
| C4 | PRP D11 uses a Unix socket; **Windows dev cannot** | Client supports both: HTTPS-free `127.0.0.1` HTTP + bearer token (dev), UDS (VPS). Local HTTP is reachable by any local process, so the token is mandatory. New env keys (`SANDBOX_TOKEN`, runtime selector) must be added to `.env.example`/CLAUDE.md list — approval requested |
| C5 | `MODEL_INFO` declares `function_calling=True`, `structured_output=True` — unverified for `gpt-6-luna` | M3 uses no tools/structured output. Stage 0 runs one tiny live probe (needs your OK) or flips both to `False` until proven. An unverified `True` is a latent lie (R-MODEL1) |
| C6 | PRP §7 requires a per-run token budget; no config key exists | Add optional `MAX_RUN_TOKENS` (unset = rely on the 12-message cap + wall-clock). Needs your OK |
| C7 | Live bridge: PRP puts the `st.fragment(run_every)` spike (U5) in M4, but the request wants real events in Livewire in M3 | Pull a **minimal** bridge into M3 (Stage 8); M4 keeps polish, replay, reduced-motion, flicker work. Needs your OK |
| C8 | Scripted design-preview scenarios still exist in the UI | Keep clearly labelled until the live path is proven (Stage 9), then decide: retain as review aid or delete. No path may mix the two |

## 4. Unresolved dependencies

| ID | Dependency | Blocking? | Needed from you |
|---|---|---|---|
| D-1 | **Docker Desktop must be running** for any sandbox test. Starting it is a host-service state change | Yes, from Stage 4 | Explicit OK to start Docker Desktop (not install). Nothing is installed or configured |
| D-2 | Execution image build (pinned `python:3.11-slim` base digest + same pins as the app for pandas/numpy/matplotlib/openpyxl). Needs one-time network pull of the base image and wheels | Yes, Stage 4 | OK for a network pull at build time only; image then runs `--network none` |
| D-3 | Live `gpt-6-luna` calls for C5 probe, Demo A, Demo B, selector-mode, follow-up (token cost). Price is not configured, so cost cannot be shown | Gate only | OK to spend live calls; optional price values if you want money figures |
| D-4 | Rootless Podman on VPS (U6): 8 read-only static checks (PRP §6.3 Phase 1) | No (dev uses Docker) | Explicit authorization before anything touches the VPS. Until then: **Go/No-go = UNKNOWN**, shipped level reported honestly as "L3 via Docker runtime (dev), VPS isolation unverified" |
| D-5 | Optional Podman-in-WSL on the dev machine for Phase 2 checks | No | Only if you want it; requires installing Podman → authorization |
| D-6 | Decisions C1–C8 above | Yes | Answers |

## 5. Risks (M3-specific, ranked)

| # | Risk | L | I | Mitigation / gate |
|---|---|---|---|---|
| X1 | Sandbox escape or leakage via broker (new attack surface) | M | H | Minimal API, fixed argv (no shell), image/flags only from broker config, token auth, §6.6 must-pass suite, REVIEW-AGENT pass |
| X2 | Docker Desktop bind-mount semantics on Windows (uid 10001, permissions, path translation) differ from Linux/Podman → false confidence | H | M | Run permission tests F3/F4 on the dev runtime; document dev as "functionally equivalent, not security-equivalent"; re-run on VPS before claiming L3 there |
| X3 | Fault injection mistaken for, or contaminating, a normal run | L | H | Separate config flag refused unless `APP_ENV=test`; `test_fault_injected` event + manifest flag + badge; Demo A asserts absence |
| X4 | Injected Coder output vs Coder's own model context disagree (Coder "remembers" the un-mutated code) → repair is unrealistic | M | M | Stage 6 spike: mutate the response **and** the stored context message; test that the fix cites the real stderr |
| X5 | Live nondeterminism flakes the gate | H | M | Scripted `ReplayChatCompletionClient` suite is the deterministic gate; live tests assert behaviours not wording; one retry policy documented, never silent |
| X6 | AutoGen API drift / maintenance mode | M | M | Pins; T-TERM contract tests; all AutoGen imports confined to `agents/` + `sandbox/executor.py` |
| X7 | Async worker vs Streamlit rerun (duplicate runs, orphaned tasks, lost events) | M | H | Run keyed by `run_id` in `st.session_state`; idempotent start; `ExternalTermination` for Stop; call-count test; cleanup on session end |
| X8 | Reviewer rubber-stamps (approval before artifacts valid) | M | H | Approval guard in `RunTerminator` (last Executor ok); static pre-checks before Reviewer (single code block, `results.json` present); full chart validators land in M5 |
| X9 | Prompt injection via dataset text | M | H | Dataset text delimited as data in prompts, sandbox is the enforcement boundary; hostile-fixture smoke test in M3, full suite M6 |
| X10 | Interpreter/venv drift (happened in M2) | M | H | Stage 0 env-integrity guard, see §7 |
| X11 | Token cost / reasoning tokens not visible in `RequestUsage` | M | L | Verify whether `completion_tokens` includes reasoning tokens (Stage 5); show totals "as reported by the model" |
| X12 | Per-execution container latency on Docker Desktop (seconds) | M | L | Timeouts sized accordingly; measured and recorded |

## 6. Implementation stages and validation gates

Every stage starts with `python scripts/check_env.py` (§7) and ends with `ruff check . && ruff format --check . && pytest -m "not live and not sandbox"` green. **I stop for review after Stage 3, Stage 7 and Stage 10** (proposed review points; you may require stops at every stage).

| Stage | Work | Owner agents | Gate to leave stage |
|---|---|---|---|
| **0 Pre-flight** | `scripts/check_env.py` + `tests/test_env_integrity.py`; record baseline in `docs/evidence/m3/env-baseline.json`; answer C1–C8; (optional, approved) C5 probe | TEST, ORCHESTRATOR | Env guard fails on a deliberately wrong interpreter (proved by test with a faked `sys.version_info`); decisions recorded in MILESTONES |
| **1 Contract spikes (offline)** | Scripted-client experiments settling U2/U3/U4 and A1–A6: task-message counting, per-message vs per-batch termination, one-turn-one-message, `stop_reason`, code-block scan scope, `NO_CODE_BLOCKS` path, selector `None` fallback, UserProxy blocking. Findings in `docs/evidence/m3/contracts.md` | AUTOGEN | Written contract per question; each pinned by a test (these become `T-TERM-1..5`) |
| **2 Termination & routing core (pure, no I/O)** | `agents/termination.py` (`RunTerminator`, `RunState`, `RunOutcome`), `agents/routing.py` (guarded `selector_func`), exact-token approval, Executor-success approval guard | AUTOGEN, TEST | **T-TERM-1..5 green**; every §3.3 table row reproduced as a test (RoundRobin and guarded); approval on message 12 = approved; no 13th message; `NOT APPROVED` / fenced / stdout / Planner `APPROVED` ignored |
| **3 Participants & prompts + events mapping** | `participants.py`, `prompts.py` (data-is-untrusted, single python block, `DATA_PATH`/`OUTPUT_DIR`, `results.json`), `events/mapping.py` (AutoGen stream → `RuntimeEvent`, real sources only), usage events, `team_factory` for both modes | AUTOGEN | Scripted-client full runs (no sandbox yet, fake `CodeExecutor` **in tests only**) reach every terminal state; reducer yields correct counter; import test: the UI process imports no code-execution path. **REVIEW POINT 1** |
| **4 Sandbox service + `BrokerCodeExecutor`** | `sandbox_service/broker/*` (stdlib server, staging, limits, `runtime_docker`, cleanup + startup reaper), execution image recipe, `sandbox/{client,executor,contracts}.py`. Fixed-argv docker CLI, `--network none --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit --memory --cpus`, tmpfs `/tmp` noexec, no env secrets, allow-listed artifact collection. `ContainerRuntime` interface keeps Podman a drop-in | SANDBOX | **Needs D-1/D-2.** `pytest -m sandbox`: full §6.6 must-pass list, including no leftover container/dir after success, error, timeout, OOM, broker restart; reported isolation level written to `docs/evidence/m3/sandbox-report.md` |
| **5 Integration with real sandbox (scripted LLM)** | Replay-client teams + real broker: error → repair, review feedback → revision, timeout, OOM, multi-block, no-block, hostile column names; usage reconciliation (message `models_usage` + selector client `total_usage()`); price handling | AUTOGEN, SANDBOX, TEST | `pytest tests/agents tests/sandbox tests/guardrails -q` green; usage totals reconcile exactly; `Pricing not configured` shown with prices unset, numeric when set |
| **6 Fault injection harness** | Test-only wrapper around Coder (first response mutated before it enters the thread; context mutation per X4); `test_fault_injected` event; config refused outside test | AUTOGEN, TEST | Unit tests: injection refused in production config; manifest flag; UI/event shows badge input; scripted run proves error → verbatim stderr in Coder input → different code → ok |
| **7 Session/follow-up (D9) & human stage** | `SessionContext` (dataset ref, bounded summaries of prior questions/answers with approval status), fresh team + fresh `RunState` per run, new `run_id`, `UserProxyAgent` with UI-driven `input_func` + timeout, outside the 12 budget | AUTOGEN | Follow-up gets a fresh 0/12 budget; prior context present as labelled data; reducer handles a second `run_id`; human decisions never affect Reviewer state. **REVIEW POINT 2** |
| **8 Live bridge (minimal; C7)** | Worker thread + own asyncio loop → `EventStore` → `st.fragment(run_every)` polling; "Run analysis" enabled only with API key + reachable broker; Stop via `ExternalTermination`; idempotent start | STREAMLIT-UI, AUTOGEN | UI tests: no duplicate run on rerun (call-count test), Livewire renders only stored events, preview and live never mixed, disabled-with-reason when key/broker missing. Spike result for U5 recorded |
| **9 Live demonstrations (needs D-3)** | **Demo A** normal run, **Demo B** labelled fault injection, selector-mode run, follow-up run. Evidence folders per PRP §8 (`manifest.json`, `events.jsonl`, `transcript.md`, `analysis.py`, artifacts, usage; no secrets) | TEST | `pytest -m live -k normal_run`, `-k fault_injection` (assertions per PRP §8); accuracy vs pandas truth on the sales fixture; honest UNAPPROVED outcome if not approved |
| **10 Review & closure** | REVIEW-AGENT security + requirements pass; no-simulation audit; update `docs/MILESTONES.md`, `docs/RISKS.md`; M3 evidence index with SHA-256 manifest | REVIEW, ORCHESTRATOR | Full non-live suite green, coverage ≥ 90% on new code, no open blocker. **STOP for your M3 approval** |

### Order dependency
0 → 1 → 2 → 3 can proceed with no Docker and no live model. Stage 4 is blocked on D-1/D-2. Stage 9 is blocked on D-3. Stage 8 can be developed against recorded events before 9.

## 7. Python 3.11 environment integrity (concrete design)

1. `scripts/check_env.py` (exit non-zero on any failure; logs, no `print`):
   - `sys.version_info[:2] == (3, 11)`; `sys.prefix` equals `<repo>/.venv` and `sys.base_prefix` contains `Python311`.
   - `.venv/pyvenv.cfg`: `version = 3.11.x` and `home` points at a 3.11 install (the M2 failure mode was a silent re-point to 3.14).
   - Every package in `requirements*.txt` installed at the exact pinned version (`importlib.metadata`); `pip check` clean; no unexpected `pyautogen`/`autogen`/`ag2` distribution (AutoGen standard).
   - Records `pyvenv.cfg` SHA-256 + Python build string into `docs/evidence/m3/env-baseline.json`.
2. `tests/test_env_integrity.py` runs the same checks inside pytest and is the first collected test (`conftest` fail-fast), so a drifted interpreter fails the gate instead of passing silently.
3. Streamlit start-up logs an error and shows a banner if the check fails; the broker and execution image assert Python 3.11 at start (the image prints its version into the run report).
4. All commands in plans/docs invoke `.venv\Scripts\python.exe` explicitly; no bare `python`.
5. Re-run at the start of every stage and immediately before each gate; mismatch → stop and report, never auto-repair.

## 8. Requirement coverage map (your nine items)

| # | Your item | Covered by |
|---|---|---|
| 1 | Real Planner, Coder, `CodeExecutorAgent`, Reviewer, UserProxy | Stages 3, 4, 7; finding A1 (exit code via broker hook), A3 (one block) |
| 2 | SelectorGroupChat routing + 12-message rule | Stages 1–2; A4–A6; C1; tables §3.3 as tests |
| 3 | Real events → EventStore → Livewire | Stage 3 (mapping), Stage 8 (bridge); C7, A8 |
| 4 | Self-correction after exec errors and Reviewer feedback | Stages 5, 6, 9; X3, X4; Demo A vs B |
| 5 | Isolated execution; Docker dev, rootless Podman VPS feasibility | Stage 4; D-1, D-2, D-4, D-5; C2–C4; X1, X2. VPS verdict stays UNKNOWN until authorized |
| 6 | Five T-TERM scenarios | Stages 1–2 (gate: all five green) |
| 7 | Usage tracking, unconfigured pricing | Stage 5; A6, X11, C5–C6 |
| 8 | Follow-ups: fresh budget, preserved context | Stage 7; D9; A8 |
| 9 | Python 3.11 integrity | Stage 0 and §7; X10 |

## 9. Explicitly NOT in M3
Final `analysis.py`/PNG/PDF exports and the one-page PDF (M5), chart-metadata validators beyond a presence check (M5), Plotly interactivity (M5), reduced-motion/replay polish (M4), full prompt-injection suite and accessibility pass (M6), Docker image for the app, Compose, Traefik, VPS (M7).

## 10. Decisions requested before Stage 0 starts

1. **C1**: Guarded Selector is the production default; RoundRobin kept only as labelled baseline. (recommended: yes)
2. **C3/C4**: Stdlib broker, JSON + dataset PUT, bearer token on localhost HTTP, UDS on VPS; add `SANDBOX_TOKEN` (and runtime selector) to env docs. (recommended: yes)
3. **C5**: allow one small live probe for function-calling/structured-output flags; otherwise set both to `False`. (recommended: probe)
4. **C6**: add optional `MAX_RUN_TOKENS`. (recommended: yes, unset by default)
5. **C7**: pull the minimal live bridge into M3. (recommended: yes)
6. **D-1/D-2**: permission to start Docker Desktop and pull the pinned base image (no installs, no config changes).
7. **Review points**: stop after Stages 3, 7, 10 only, or at every stage?
8. Authorization status for D-4 (VPS read-only inspection) and D-5 (Podman in WSL): **default = not authorized**.

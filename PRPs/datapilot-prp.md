# PRP: DataPilot — Self-Correcting Data Analyst

> Implementation blueprint. Source of truth: `docs/SocialEagle_UseCase_Definitions.pdf` (Use Case 03, pp. 9–11) + `INITIAL.md`.
> Execute **one milestone at a time** with `/execute-prp PRPs/datapilot-prp.md --milestone M<n>`.

---

## 0. METADATA

| Field | Value |
|---|---|
| Product | DataPilot — Self-Correcting Data Analyst (learning assignment, not SaaS) |
| PRP version | 1.1 (corrections after final review, 2026-10-15) |
| Complexity | High (agent routing, sandbox broker, event-driven UI) |
| Milestones | M2–M7 (M1 approved) |
| Decisions status | D3 = **L3 target** (approved); D9, D10, D12 approved; D11 conditional; D1, D2, D4–D8 planning assumptions subject to validation gates (§12) |

---

## 1. PRODUCT OVERVIEW

Ask a sales question in plain English; AutoGen agents plan, write pandas/matplotlib code, run it in an isolated sandbox, repair their own errors, are reviewed, and return a verified answer + PNG charts + `analysis.py` + one-page PDF.

**Primary acceptance criterion:** real autonomous correction. A real execution error is returned verbatim to the real Coder, which writes a real fix that the real Executor reruns, without human debugging. No scripted correction, no hardcoded answer.

**MVP = full assignment + all three stretch goals** (SelectorGroupChat, multi-sheet Excel, one-page PDF).

---

## 2. TECH STACK AND VERIFIED FACTS

### 2.1 Stack (pins resolved at M2; do not add packages without approval)

| Layer | Choice | Pin policy |
|---|---|---|
| Runtime | Python 3.11 | explicit venv/image; `requires-python = ">=3.11,<3.12"` |
| Agents | `autogen-agentchat`, `autogen-ext[openai]` | newest matching pair (last confirmed 0.7.5, Sept 2025 — **re-verify on PyPI**) |
| LLM | `OPENAI_MODEL=gpt-6-luna` | env only |
| UI | Streamlit | pin at M2; needs `st.fragment(run_every=…)` (verify min version) |
| Data | pandas, openpyxl, numpy | pin |
| Charts | matplotlib (Agg, PNG), Plotly | pin |
| PDF | ReportLab | pin |
| HTTP (broker client, model check) | `httpx` | **approved (D12)**; pin; justified: broker API client and the M2 model check |
| Settings | `pydantic-settings` | **approved (D12)**; pin; justified: env-only typed configuration, no hardcoded secrets/model id |
| Tests | pytest, `pytest-asyncio`, pytest-cov | `pytest-asyncio` **approved (D12)**; pin; justified: AutoGen `run_stream` and the broker client are async |
| UI tests | Playwright | **approved (D12)**; pin; justified: required viewport/overflow/screenshot checks (INITIAL §12–13); dev-only, not in the app image |
| Lint | Ruff | pin |
| Containers | Docker Compose (app, Traefik); Podman rootless (sandbox executions, if feasible) | — |

### 2.2 AutoGen API facts verified from the stable reference docs (2026-10-15)

| Topic | Verified fact | Source |
|---|---|---|
| `TextMentionTermination` | `(text, sources=None)`; **`sources` exists** → can restrict to Reviewer. Substring match: `"NOT APPROVED"` would match → need stricter check | `autogen_agentchat.conditions` |
| `MaxMessageTermination` | `(max_messages, include_agent_event=False)`; counts `BaseChatMessage` only by default; **docs do not say whether the task message counts** | same |
| Other conditions | `FunctionalTermination`, `SourceMatchTermination`, `TextMessageTermination`, `HandoffTermination`, `ExternalTermination`, `TimeoutTermination`, `TokenUsageTermination`, `StopMessageTermination`, `FunctionCallTermination` | same |
| `SelectorGroupChat` | `(participants, model_client, *, termination_condition, max_turns, selector_prompt, allow_repeated_speaker=False, max_selector_attempts=3, selector_func, candidate_func, emit_team_events=False, model_client_streaming=False, model_context)`. `selector_func` overrides the model; **returning `None` falls back to the model**. `candidate_func` ignored when `selector_func` set. | `autogen_agentchat.teams` |
| `RoundRobinGroupChat` | `(participants, *, termination_condition, max_turns, emit_team_events=False, …)`; no model client | same |
| Team state | `reset()` (team must be stopped), `save_state()`, `load_state()` | same |
| `CodeExecutorAgent` | `(name, code_executor, *, model_client=None, max_retries_on_error=0, sources=None, supported_languages=['python','sh'], approval_func=None, …)`. **Without `model_client` it only executes fenced code blocks found in incoming messages.** `sources` filters whose messages are scanned (only when no model_client). | `autogen_agentchat.agents` |
| `AssistantAgent` | `(name, model_client, *, tools, system_message, model_client_stream, reflect_on_tool_use, …)`; not thread/coroutine-safe | same |
| `UserProxyAgent` | `(name, *, description, input_func)`; input_func sync or async, may take `CancellationToken`; **blocks a running team** until input; docs recommend `HandoffTermination`/`SourceMatchTermination` to return control to the app | same |
| `CodeExecutor` ABC | abstract `execute_code_blocks(code_blocks, cancellation_token) -> CodeResult`, `start()`, `stop()`, `restart()`; `CodeBlock{code, language}`, `CodeResult{exit_code, output}` | `autogen_core.code_executor` |
| `OpenAIChatCompletionClient` | `model_info` **required for non-OpenAI-listed model names** with fields `vision, function_calling, json_output, family, structured_output` (opt `multiple_system_messages`); `temperature`, `seed`; `total_usage()` / `actual_usage()` per client; streaming usage needs `include_usage` | `autogen_ext.models.openai` |
| Event classes | `TextMessage, ToolCallSummaryMessage, HandoffMessage, StopMessage` (chat); `CodeGenerationEvent, CodeExecutionEvent, ToolCallRequestEvent/ExecutionEvent, SelectSpeakerEvent, ModelClientStreamingChunkEvent, ThoughtEvent, UserInputRequestedEvent` (events). Each has `source`, `models_usage`, `created_at`. | `autogen_agentchat.messages` |

### 2.3 Still UNVERIFIED (must be settled by a spike in the named milestone)

| ID | Question | Settled by |
|---|---|---|
| U1 | Does `gpt-6-luna` exist/answer on the key's account; correct `model_info`; supported params; price table | **M2 step 0** live compatibility check (M2) |
| U2 | Installed-library semantics: is the task message counted/passed to termination conditions; is termination evaluated per message or per batch; can one agent turn emit more than one chat message | M3 `T-TERM-1..5` (§3.2) |
| U3 | `CodeExecutionEvent` field set; does `CodeExecutorAgent` w/o model client emit it | M3 step 2 (inspect installed source) |
| U4 | `TaskResult.stop_reason` contents and the final stream item shape | M3 step 2 |
| U5 | Streamlit `st.fragment(run_every)` + worker-thread update behaviour on the pinned version | M4 spike |
| U6 | Rootless Podman feasibility on the VPS (§6.3) | M3 pre-gate + M7 inspection (read-only) |
| U7 | `autogen-agentchat` status: the project README states AutoGen is in **maintenance mode** and recommends Microsoft Agent Framework for new work. The assignment mandates AutoGen; keep AutoGen, pin versions, record the risk | M2 |

---

## 3. ARCHITECTURE

```
 Browser ──HTTPS──> Traefik ──> app (Streamlit, py3.11)
                                  │  UI thread: renders from EventStore (st.fragment)
                                  │  Worker thread (asyncio): AutoGen team.run_stream
                                  │      Planner · Coder · Executor · Reviewer  (+ guarded Selector)
                                  │      Executor = CodeExecutorAgent(code_executor=BrokerCodeExecutor)
                                  │  UserProxyAgent (post-loop human stage)
                                  ▼  HTTP / unix socket (narrow broker API only)
                          sandbox broker  (separate process; owns the container runtime)
                                  ▼  per execution
                          ephemeral container (L3): no network, read-only rootfs, caps dropped,
                          pids/mem/cpu limits, ro dataset mount, rw output dir, destroyed after run
```

### 3.1 Agent message flow and termination state machine

Baseline `RoundRobinGroupChat([Planner, Coder, Executor, Reviewer])` — **the speaker order is a fixed cycle P → C → E → R → P → C → …**, so after a Reviewer reply the next speaker is the *Planner*, not the Coder, and after an Executor error the next speaker is the Reviewer. Guarded mode is `SelectorGroupChat` with `selector_func`:

| Last speaker/outcome | Next (guarded selector_func) | Else |
|---|---|---|
| (start) | Planner | |
| Planner | Coder | |
| Coder (code block present) | Executor | return `None` → LLM picks (Coder again if no code) |
| Executor `exit_code != 0` or timeout | **Coder** (always) | |
| Executor ok | Reviewer | |
| Reviewer not approved | **Coder** | |
| Reviewer approved | (terminate) | |

`selector_func` returns `None` only where the LLM may legitimately choose (stretch goal 1 evidence); error routing is never left to the LLM.

Terminal states (mutually exclusive): `REVIEWER_APPROVED`, `LIMIT_REACHED(12)`, `ERROR(infra)`. Human stage is a **separate** state machine: `PENDING → APPROVED | REJECTED | FOLLOW_UP`. An unapproved run is labelled UNAPPROVED/INCOMPLETE everywhere and never offers "verified" artifacts without that label.

### 3.2 What counts toward the 12-message limit, and how termination works

**Definition (normative).** An *agent message* is a chat message (a `BaseChatMessage`, e.g. `TextMessage`) produced during the run by one of the four autonomous participants: Planner, Coder, Executor, Reviewer. One speaking turn produces exactly one counted message.

| Counts toward 12 | Does **not** count |
|---|---|
| Planner plan; Coder code or fix; Executor result (success **or** error); Reviewer feedback / relay / `APPROVED` | the user's initial task message; any `BaseAgentEvent` (code-generation, tool-call, speaker-selection, streaming-chunk, thought events); executor hook events; guardrail/usage/test events; User Proxy / human-stage messages (post-loop); the final `TaskResult` |

The counter is app-owned (`agents/termination.py`), counts only the four source names, starts at 0 per run, **never resets within a run**, and is exposed to the UI as `n/12`.

**Termination logic.** One custom termination condition (`RunTerminator`) is evaluated on every new agent message, in this order:

1. If the message is from `Reviewer`, its last non-empty line equals `APPROVED` exactly (case-sensitive, standalone), and the most recent Executor result was successful → **`REVIEWER_APPROVED`**.
2. Else if `count >= 12` → **`LIMIT_REACHED`**.
3. Else continue.

Consequences: a valid Reviewer approval that is message number 12 is **approved**, not limited (approval is checked first); message 13 can never be produced; `APPROVED` from any other source, inside a code block, in stdout, or as part of "NOT APPROVED" is ignored; a Reviewer `APPROVED` after a failed execution is ignored (it still counts as a message).
The stop reason is stored in app state (`RunOutcome`), not parsed from the library's free-text `stop_reason`. `TextMentionTermination("APPROVED", sources=["Reviewer"])` is rejected as the only mechanism (substring match). `TimeoutTermination` (wall clock) and `ExternalTermination` (UI Stop) give additional outcomes `TIMEOUT` / `STOPPED`, never presented as verified.

**M3 verification against the installed AutoGen API (blocking):**

| Test | Asserts |
|---|---|
| `T-TERM-1` | with a scripted client, our counter excludes the task message and stops after exactly 12 agent messages; records (informational) whether the library's own `MaxMessageTermination` counts the task |
| `T-TERM-2` | boundary: Reviewer `APPROVED` as message 11 and as message 12 → approved; a non-approving 12th → `LIMIT_REACHED`; no 13th message exists in the event log |
| `T-TERM-3` | termination is evaluated per message (not only per batch) and a turn never yields two counted chat messages; if it can, truncate at the cap and add a test |
| `T-TERM-4` | `NOT APPROVED`, `APPROVED` in a code fence / stdout / Planner message, and approval after a failed execution do not terminate |
| `T-TERM-5` | final `TaskResult` shape recorded; `RunOutcome` is correct for every outcome |

### 3.3 Budget arithmetic (normative; mirrored by tests)

Notation: P Planner, C Coder, E Executor, R Reviewer; `E✗` execution error, `E✓` success. Each token below is **one counted message**.

**RoundRobin (fixed cycle P C E R; one loop = 4 messages; three loops = 12):**

| Scenario | Sequence | Messages | Outcome |
|---|---|---|---|
| Clean pass | P C E✓ R(APPROVED) | **4** | approved |
| One exec error, then approved | P C E✗ R(relay) · P C E✓ R(APPROVED) | **8** | approved |
| One exec error + one Reviewer-feedback round (the PDF sample) | P C E✗ R(relay) · P C E✓ R(feedback) · P C E✓ R(APPROVED) | **12** | approved **on the 12th message** |
| Two feedback rounds, no errors | P C E✓ R(fb) · P C E✓ R(fb) · P C E✓ R(APPROVED) | **12** | approved on the 12th |
| Two exec errors + one feedback round | P C E✗ R · P C E✗ R · P C E✓ R(fb) · P C E✓ R(APPROVED) | 16 → stops at 12 | `LIMIT_REACHED` (UNAPPROVED) |

RoundRobin has a budget of exactly **three loops**; every loop pays for a Planner turn (a terse "plan unchanged") and, on errors, a Reviewer relay.

**Guarded `SelectorGroupChat` (Executor✗ → C, Reviewer✗ → C; no Planner repeat):**

| Scenario | Sequence | Messages | Outcome |
|---|---|---|---|
| Clean pass | P C E✓ R(APPROVED) | **4** | approved |
| One exec error, then approved | P C E✗ C E✓ R(APPROVED) | **6** | approved |
| One exec error + one feedback round | P C E✗ C E✓ R(fb) C E✓ R(APPROVED) | **9** | approved |
| Two exec errors + one feedback round | P C E✗ C E✗ C E✓ R(fb) C E✓ R(APPROVED) | **11** | approved |
| Three exec errors + one feedback round | P C E✗ C E✗ C E✗ C E✓ R(fb) C E✓ R(APPROVED) | 13 → stops at 12 | `LIMIT_REACHED` |

Consequence (D4): guarded routing is the UI default because it recovers from more failures within 12 messages; RoundRobin remains the assignment baseline and test target. The earlier version of this table (clean pass = 5, Reviewer relay only) was wrong and is superseded.

### 3.4 Runtime agents

| Agent | Class | Notes |
|---|---|---|
| Planner | `AssistantAgent` | input: question + compact profile (columns, dtypes, null counts, date columns, 5 sample rows delimited as data). Output: numbered plan. |
| Coder | `AssistantAgent` | single fenced ```python block; reads `DATA_PATH` (env/argv), `SHEET` if Excel; writes charts to `OUTPUT_DIR`, writes `results.json`; deterministic; no network; `matplotlib.use("Agg")`. |
| Executor | `CodeExecutorAgent(code_executor=BrokerCodeExecutor, sources=["Coder"], model_client=None)` | executes Coder's block verbatim; emits stdout/stderr via executor hook events. |
| Reviewer | `AssistantAgent` | checks per assignment §3.2; sees Executor output + `results.json` summary + chart metadata; replies `APPROVED` alone on last line or numbered feedback. |
| User Proxy | `UserProxyAgent` | post-loop; `input_func` awaits a UI decision (approve / reject / follow-up text) with `CancellationToken` timeout. Outside the autonomous loop (C3). |

### 3.5 Event model (`src/datapilot/events/models.py`)

One normalized, immutable `RuntimeEvent{seq, run_id, ts, type, source, payload}`. **No event is synthesized without a real source.**

| `type` | Real source | Payload |
|---|---|---|
| `run_started` | app on submit | question, dataset fingerprint, mode |
| `speaker_selected` | `SelectSpeakerEvent` (`emit_team_events=True`) or RoundRobin order | next agent |
| `agent_message` | `TextMessage` | source, content, tokens |
| `code_generated` | Coder `TextMessage` containing a code block (parsed) | code, hash |
| `exec_started` | `BrokerCodeExecutor` entry hook | code hash, run id |
| `exec_result` | `BrokerCodeExecutor` result hook | status, exit_code, stdout, stderr, duration, artifacts |
| `repair_routed` | derived: `exec_result.status != ok` and next speaker == Coder (observed) | attempt n |
| `review_feedback` | Reviewer message not approving | text |
| `reviewer_approved` | approval termination fired | message seq |
| `limit_reached` | cap termination fired | count |
| `terminated` | `TaskResult.stop_reason` | reason, totals |
| `guardrail` | guardrail module | rule, outcome |
| `usage` | `models_usage` / client `total_usage()` | tokens, est. cost |
| `human_*` | UI/UserProxy | decision |

---

## 4. MODULES

Layout (created progressively; only these are allowed without approval):

```
src/datapilot/
  config.py                      # pydantic-settings, env only
  logging_setup.py               # structured JSON logging
  ingestion/{loader,profile,validate,models}.py
  agents/{prompts,participants,teams,routing,termination,human,client,usage}.py
  events/{models,store,mapping,reducer}.py
  sandbox/{executor,client,contracts}.py        # app side
  reports/{results,charts_check,script_export,pdf}.py
  guardrails/{upload,injection,code_policy,approval}.py
  evals/{accuracy,repro,artifacts}.py
  ui/{app,theme,state,workspaces/{explore,livewire,insights}.py,components/*.py}
sandbox_service/                 # broker + image recipe (separate container/process)
  broker/{main,runtime_podman,runtime_docker,limits,staging}.py
  image/Dockerfile               # execution image (py3.11, pandas, matplotlib, openpyxl)
tests/{ingestion,agents,sandbox,events,reports,guardrails,evals,ui,live}/
fixtures/{sales_sample.csv(12,480 rows), sales_alt_schema.csv, multisheet.xlsx, generate.py}
```

### 4.1 Ingestion
`load_dataset(path, sheet=None) -> Dataset`; `list_sheets(path)`; `profile(df) -> DatasetProfile{rows, columns[{name,dtype,nulls,sample}], date_columns, quality_flags}`; validation: extension+magic bytes, size ≤ `MAX_UPLOAD_MB`, rows/cols caps, xlsx zip-bomb guard (uncompressed size cap, no external links/macros processed), non-empty, duplicate column names.
Schema-agnostic; two fixture schemas required.

### 4.2 Agents
`build_team(mode: Literal["round_robin","selector"], deps) -> Team`; `run_question(question, dataset, mode) -> AsyncIterator[RuntimeEvent]`; usage + cost with price table in config (price for `gpt-6-luna` unknown → required config key, no default).

### 4.3 Sandbox (app side)
`BrokerCodeExecutor(CodeExecutor)`: stages dataset and code via broker, returns `CodeResult(exit_code, output)` with stdout+stderr composed, plus hook events carrying the structured result. Contract in §6.

### 4.4 Reports
`results.json` schema (Coder-written, validated): `{answer_facts: [{label, value, unit}], tables: [...], charts: [{file, title, x_label, y_label, unit}]}`. Static validators: every chart has title/axis labels/unit; every number the narrative cites is present in `results.json` or stdout. `script_export`: final `analysis.py` = last successfully executed code, verbatim, plus header; `pdf`: ReportLab, A4, **exactly one page** (answer, key numbers, ≤2 charts, verification status, timestamp excluded from reproducibility checks).

### 4.5 UI
Three workspaces per `INITIAL.md §8`, design tokens per `skills/BI_UI.md`; Livewire per `skills/LIVEWIRE.md`; bridge per `skills/STREAMLIT.md`.

### 4.6 Guardrails / evals / observability
Guardrails emit `guardrail` events. Evals run against fixtures: accuracy vs pandas ground truth, reproducibility (rerun script in sandbox twice → identical `results.json` hash), artifact validity. "Behind the Scenes" panel renders the event log, evals, usage, termination reason; secrets redacted at the logging layer.

---

## 5. MILESTONES

Each milestone: owner dev-agents · tasks · deliverables · gate · exit criteria. Log times + rework in `docs/MILESTONES.md`. Stop at each gate.

### M2 — Foundation & premium UI shell
**Agents:** STREAMLIT-UI-AGENT, TEST-AGENT, DEVOPS-AGENT (dev env only) · **Skills:** STREAMLIT, BI_UI, TESTING
Steps run in this order; **step 0 and the mockup approval are hard gates.**

0. **GPT-6 Luna compatibility check — the first action of M2, before any other M2 work.** Requires `OPENAI_API_KEY` and `OPENAI_MODEL=gpt-6-luna` in the environment (stop and ask if absent). Using only the packages needed (`httpx`, the pinned AutoGen OpenAI client, in the new py3.11 venv), run `scripts/check_model.py`, which makes **one** minimal live exchange and records:
   - availability: model retrieval (`GET /v1/models/gpt-6-luna`) and one minimal chat completion;
   - basic response behaviour: non-empty text, finish reason, usage fields (prompt/completion tokens);
   - parameter compatibility: `temperature`, `seed`, `max_tokens` vs `max_completion_tokens`;
   - the `model_info` AutoGen needs (`vision`, `function_calling`, `json_output`, `family`, `structured_output`), confirmed by `OpenAIChatCompletionClient` completing a call with it;
   - the pricing keys the config must carry (price is user-supplied; none assumed).
   Output: `docs/evidence/m2/model-check.md` (no secrets). **If the model is unavailable or incompatible: stop M2, report the exact error and ask for approval. Never substitute a model.**
1. py3.11 venv via `py -3.11`; `pyproject.toml`; pinned requirements (including the D12 packages); Ruff/pytest config (markers `live`, `sandbox`, `ui`). Confirm AutoGen versions on PyPI and record the maintenance-mode risk (D10 approved).
2. Fixture generator (12,480-row PDF-shaped CSV, alt schema, multi-sheet xlsx) with ground truth.
3. Ingestion module + tests (CSV, xlsx, multi-sheet, invalid/oversize files). Non-visual; may proceed before mockup approval.
4. Event models, `EventStore`, reducer skeleton (no AutoGen run yet). Non-visual.
5. **UI mockups (design only; no shell code).** Produce static mockups in `docs/mockups/` (HTML/CSS or PNG) for Ask & Explore; Agent Livewire in idle, running, exec-error, repair, reviewer-feedback, approved, limit-reached and fault-injection-badge states; and Insights Studio — each at 1920 and 390 widths — plus a design-token sheet and a table mapping each visual state to a `RuntimeEvent`. Check them against the anti-pattern list in `skills/BI_UI.md`.
   **Mockup approval gate:** the user approves the mockups in writing and the approval is recorded in `docs/MILESTONES.md`. **No Streamlit visual shell, theme or Livewire canvas code may be written before this approval.** Requested changes count as rework cycles.
6. After approval: theme + app shell with three workspaces; Ask & Explore functional (upload, sheet select, profile, preview, composer); Livewire and Insights present as structured, non-simulated empty states matching the approved mockups.
**Gate:** `ruff check . && pytest -m "not live and not sandbox" -q`; step-0 evidence present and green; mockup approval recorded; `streamlit run` manual review; Playwright overflow checks at 4 viewports; screenshots in `docs/screens/m2/` compared with the mockups.
**Exit:** model check passed; ingestion tests green; shell matches approved mockups and is user-reviewed; versions pinned.

### M3 — Real AutoGen execution engine
**Agents:** AUTOGEN-AGENT, SANDBOX-AGENT, TEST-AGENT · **Skills:** AUTOGEN, SANDBOX, TESTING
**Pre-gate (read-only; nothing installed):** the sandbox feasibility checks of §6.3. Build against the `ContainerRuntime` interface using the Docker-backed dev runtime meanwhile. The `gpt-6-luna` check was done in M2 (U1) and is re-run only if configuration changes.
1. `T-TERM-1..5` (§3.2) against the installed AutoGen version → settles U2 and the counting definition in code.
2. Inspect the installed AutoGen source for `CodeExecutionEvent` and `TaskResult` → settles U3/U4.
3. Participants, prompts, `BrokerCodeExecutor`, broker service (staging, limits, runtime adapter, cleanup + startup reaper), routing guard, `RunTerminator`, human stage (`UserProxyAgent`).
4. Scripted-client orchestration tests with the real sandbox, covering every row of the §3.3 tables.
5. **Two separate live demonstrations (§8):** (A) a normal, non-injected analytical run; (B) a clearly labelled, test-only fault-injection run proving genuine autonomous repair.
**Gate:** `pytest tests/agents tests/sandbox tests/guardrails -q`; `pytest -m live -k normal_run`; `pytest -m live -k fault_injection`; sandbox must-pass list (`skills/SANDBOX.md`, §6.6).
**Exit:** `docs/evidence/m3/normal-run/` and `docs/evidence/m3/fault-injection/` both present with manifests (§8); Reviewer-only approval and approval-on-12th proven; 12-cap proven; isolation level reported (L3, or a declared fallback pending approval).

### M4 — Live Agent Livewire
**Agents:** STREAMLIT-UI-AGENT, AUTOGEN-AGENT, TEST-AGENT · **Skills:** LIVEWIRE, STREAMLIT
1. Spike U5: worker thread + EventStore + `st.fragment(run_every)`; fallback `st.empty()` placeholders; choose and record.
2. SVG/CSS canvas with reducer `events → CanvasState`; lanes, loop-back arcs, counter /12, human node separate.
3. Timeline + inspector (code, stdout, stderr, feedback, guardrails, tokens).
4. Reduced-motion; keyboard focus; responsive lane layout.
**Gate:** `pytest tests/events tests/ui -q`; replay test of a recorded real run; manual live run watched by user.
**Exit:** no simulated data path exists (code review); no flicker; no duplicate model calls on rerun (call-count test).

### M5 — Insights & stretch goals
**Agents:** STREAMLIT-UI-AGENT, AUTOGEN-AGENT, TEST-AGENT · **Skills:** BI_UI, TESTING
1. `results.json` contract end-to-end; Insights Studio (KPI strip, coordinated Plotly visuals, tables, narrative, verification, approvals).
2. `analysis.py` export + sandbox rerun reproducibility check; PNG downloads; one-page PDF.
3. Multi-sheet Excel end-to-end (sheet selection feeds the run); SelectorGroupChat mode switch in UI.
4. Human approval via `UserProxyAgent`; same-session follow-up (new run, prior context summary).
**Gate:** `pytest tests/reports tests/evals -q`; live run on PDF-shaped fixture with accuracy eval.
**Exit:** Done Checklist items 4–6 demonstrably green.

### M6 — Quality & validation
**Agents:** TEST-AGENT, REVIEW-AGENT · **Skills:** TESTING, SANDBOX
Prompt-injection suite (hostile cell text/column names); guardrail coverage; eval suite; API-efficiency budget test; responsive screenshots at 1920/1366/820/390; accessibility pass; REVIEW-AGENT report; user visual sign-off.
**Gate:** full `pytest -m "not live"`, coverage report, `pytest -m live`, REVIEW findings with no open blockers.

### M7 — Docker, VPS & closure
**Agents:** DEVOPS-AGENT, REVIEW-AGENT · **Skills:** DEPLOYMENT, SANDBOX
Read-only VPS + Traefik inspection → approval → image build → compose deploy → HTTPS/WebSocket verification → sandbox egress and secret checks → rollback test → `docs/DEPLOY.md` → README final → completion report.
**Gate:** §9 verification checklist.

---

## 6. SANDBOX: L3 PER-EXECUTION ISOLATION (decision D3)

### 6.1 Target and fallbacks

| Rank | Option | Status |
|---|---|---|
| **Target** | **L3-a** Rootless Podman broker, one container per execution | Approved target; feasibility unverified |
| Fallback 1 | **L3-d** Same broker with Docker as runtime (`docker run --rm` with the same flags), broker running as an unprivileged process | Needs approval: runtime access to the Docker daemon is held by the broker, **not** the app |
| Fallback 2 | **L2** long-running service, subprocess per run | Only with explicit user approval; must be reported as weaker |
| Rejected | Docker socket in app; DinD/privileged; local-folder execution | — |

### 6.2 Broker design

- **Where it runs (D11):** as an unprivileged *host* service under a dedicated user (`dpsandbox`) invoking rootless Podman, exposing only a Unix socket (`/run/datapilot-sandbox/broker.sock`, mode 0660, group-shared with the app container's mapped gid) with the narrow API below. **Not** Podman-in-Docker, which would require privileged/device access.
- The app container never receives the Docker or Podman socket — only the broker API socket.
- **Broker API:** `POST /v1/runs` (multipart: `code`, `dataset` or `dataset_id`, `session_id`, `timeout_s`) → `{run_id, status, exit_code, stdout, stderr, duration_ms, artifacts[{name,size,sha256}], truncated}`; `GET /v1/runs/{id}/artifacts/{name}`; `DELETE /v1/runs/{id}`; `GET /healthz`. No generic exec, no arbitrary image or flags: image and limits are broker config.
- **Per execution:** create run dir (`0700`, owner `dpsandbox`) → stage `analysis.py` + dataset (read-only copy) → `podman run --rm --network none --read-only --cap-drop all --security-opt no-new-privileges --pids-limit N --memory M --cpus C --timeout T --tmpfs /tmp:rw,size=64m,noexec --user 10001 --mount type=bind,src=<run>/in,dst=/in,ro=true --mount type=bind,src=<run>/out,dst=/out <pinned-image> python /in/analysis.py` (flags exist per Podman docs; `--user`/`--userns` handling to be confirmed on the host) → collect allow-listed artifacts (regular files, name regex, size cap, no symlinks) → destroy container + run dir.
- Environment inside the container: `DATA_PATH`, `OUTPUT_DIR`, `MPLBACKEND=Agg`, `PYTHONHASHSEED=0`, `TZ=UTC` — **no** OpenAI key, no host env.
- Image: pinned digest; contains py3.11, pandas, numpy, matplotlib, openpyxl only; no pip at runtime; built/loaded offline.
- Timeouts at three layers: container `--timeout`, broker wall-clock kill + `podman rm -f`, executor-side client timeout.

### 6.3 Feasibility checks (L3 is the approved target; nothing is installed or changed without approval)

**Phase 1 — VPS static inspection (read-only; run only after approval):**

| # | Check | Command (read-only) | Go condition |
|---|---|---|---|
| 1 | Virtualization/kernel | `systemd-detect-virt; uname -r` | KVM/full VM; kernel ≥ 5.11 preferred |
| 2 | User namespaces | `cat /proc/sys/user/max_user_namespaces` | > 0 |
| 3 | cgroups v2 + delegation | `stat -fc %T /sys/fs/cgroup; cat /sys/fs/cgroup/user.slice/user-*.slice/cgroup.controllers` | cgroup2fs; memory, pids, cpu delegable (otherwise limits are silently unenforced) |
| 4 | **UID/GID mapping prerequisites** | `grep -E '^' /etc/subuid /etc/subgid; command -v newuidmap newgidmap` | ≥ 65 536 sub-IDs available for the broker user; `newuidmap`/`newgidmap` present |
| 5 | Package availability | `apt-cache policy podman` (or distro equivalent) | podman ≥ 4.x installable |
| 6 | **Docker/Traefik compatibility** | `docker ps; docker network ls; ss -ltnp` + read existing Traefik config | no port/network conflict; Podman storage separate from Docker; Traefik, its networks and other stacks untouched |
| 7 | Resources | `free -m; df -h; nproc` | headroom for concurrent runs and the execution image |
| 8 | **Unix socket path & permissions** | inspect `/run` permissions, existing groups, systemd availability | a `0750` directory and a `0660` socket under a dedicated group are creatable |

**Phase 2 — functional verification (needs Podman installed → explicit approval first; may be done earlier on the dev machine):**

| # | Check | How | Pass condition |
|---|---|---|---|
| F1 | Rootless run works | `podman run --rm --network none --read-only … <image> python -c 'print(1)'` as the broker user | exit 0, output captured |
| F2 | **Container timeout semantics** | infinite loop and `sleep` with `--timeout`; also broker wall-clock kill | killed within tolerance; known exit code (e.g. 124/137) mapped to `status=timeout`; `--rm` still removes the container; no zombie conmon/process |
| F3 | **UID/GID mapping** | write from container uid 10001 into `/out`; read from the broker user; compare `--userns=keep-id` with default | artifacts readable and removable by the broker; no root-owned files; container user cannot write `/in` |
| F4 | **Dataset & artifact mount permissions** | `/in` bind `ro=true`; `/out` writable; try writing to `/in` and `/`, traversal, symlink out of `/out` | writes outside `/out` fail; symlink/escape artifacts rejected by the broker |
| F5 | **Unix socket permissions** | connect as the app's uid/group, as another uid, as no group; check `SO_PEERCRED` | only the app's group connects; others get EACCES; socket not world-accessible; no Docker/Podman socket exposed to the app |
| F6 | **Cleanup after execution** | after success, error, timeout, OOM, broker crash/restart | `podman ps -a`, volumes, run dirs and tmpfs are empty; startup reaper removes strays |
| F7 | Limits enforced | memory hog, fork bomb, CPU spin | `--memory`, `--pids-limit`, `--cpus` enforced (proves cgroup delegation) |
| F8 | **Coexistence** | run F1–F7 while Traefik and the other apps serve traffic | no change in their health/latency; no firewall or network rule changes |

**Deliverable:** a Go / No-go report per row with the fallback decision. Decision D11 (host-level broker) is conditional on this report **and** explicit deployment approval. **Do not install Podman, create users/groups, edit systemd, change sub-ID files, or touch Traefik or other apps without approval.**

### 6.4 Windows dev machine
Local dev uses the same broker process with `runtime_docker` (Docker Desktop) so the *application code path is identical*; the broker runs on the developer host, the app talks to it over localhost HTTP. Podman-on-WSL is optional. No code in the app depends on which runtime is behind the broker.

### 6.5 Residual risks (to be stated in the final report)
Kernel shared with the host (only gVisor/Kata would help — out of scope); a runtime/kernel escape bug breaks isolation; broker is a privileged-adjacent component and must have a minimal, tested API; image supply chain; per-run container start latency (hundreds of ms to seconds).

### 6.6 Must-pass sandbox tests
no network (DNS + TCP) · no secrets in env · cannot read broker/host files · cannot read another run · cannot write outside `/out` · traversal/symlink artifacts rejected · infinite loop → `timeout` · memory hog → `killed` · fork bomb bounded · **no container/process/file left after a run (success, error, timeout, crash)** · deterministic output for identical code+data · broker API rejects extra flags/images · container timeout maps to `status=timeout` and removes the container · artifact ownership/permissions correct · socket rejects non-members.

---

## 7. GUARDRAILS

| Area | Rule |
|---|---|
| Upload | type/magic/size/rows/cols/zip-bomb; reject encrypted or macro-enabled |
| Prompt injection | dataset text delimited and labelled as data; Planner/Coder/Reviewer prompts state data has no authority; Reviewer checks code against `code_policy` (no network libs, no `os.environ`, no subprocess, no file access outside `DATA_PATH`/`OUTPUT_DIR`); sandbox is the enforcement boundary |
| Approval | Reviewer-only exact token; refuse approval after failed exec; refuse if chart metadata missing |
| Limits | 12 messages; wall-clock; sandbox timeout; token budget per run (config) |
| Secrets | never in prompts, sandbox, logs, UI; log redaction filter |
| Output | no unapproved analysis presented as verified; UNAPPROVED banner |
| Efficiency | profile compaction, no replanning on retry, one Reviewer call per successful exec, no LLM call on UI rerun |

---

## 8. TEST PLAN

| Layer | Marker | Contents |
|---|---|---|
| Unit | default | ingestion, profile, validators, reducers, termination predicates, routing function, usage/cost |
| Orchestration | default | **scripted model client**, real sandbox: error→repair, review→revision, Reviewer-only approval, `NOT APPROVED`/code/stdout `APPROVED` ignored, 12-cap (incl. §3.3 table), selector guard, follow-up, human stage |
| Sandbox | `sandbox` | §6.6 |
| Artifacts | default | chart labels/units, results schema, `analysis.py` rerun identical, PDF 1 page |
| UI | `ui` | Playwright overflow/clipping at 1920×1080, 1366×768, 820×1180, 390×844; reduced motion; screenshots |
| Evals | default | numeric accuracy vs pandas truth on 2 schemas |
| Efficiency | default | LLM call count ≤ budget; zero calls on rerun |
| Live | `live` | real `gpt-6-luna`: **Demo A** normal run; **Demo B** labelled fault-injection autofix; selector mode; follow-up |

### Autonomous-correction evidence: two separate live demonstrations

| | Demo A — normal run | Demo B — fault-injection run (test-only) |
|---|---|---|
| Purpose | show the system analysing real data end-to-end exactly as in production | prove genuine autonomous repair when an error is guaranteed |
| Setup | PDF-shaped fixture + reference question; **no hooks, no mutation** | same fixture/question + `FAULT_INJECTION=coder_first_output` (test config only; refused in production config) |
| What is injected | nothing | the **Coder's first code message** is mutated *before it enters the conversation* (e.g. a column reference renamed or an undefined name added), so the faulty code is what every agent sees and the real Executor runs |
| Repair | whatever happens naturally; may include a natural error or none | the **real Coder** receives the real Executor error (stderr) and writes the correction; no canned repair |
| Claim allowed | "normal run"; may claim self-correction **only if a natural error actually occurred** | "autonomous repair under injected fault" — always labelled |
| Evidence | `docs/evidence/m3/normal-run/` | `docs/evidence/m3/fault-injection/` |

Rules:
- A `test_fault_injected` event (source: test harness) is emitted, shown in Livewire and Behind the Scenes with a persistent **"TEST FAULT INJECTED"** badge, and written to the manifest (`injected: true`, what was mutated, original vs mutated hash).
- Injected faults are **never** presented as naturally occurring errors anywhere (UI, README, report).
- Demo B assertions: ≥1 `exec_error`; the next Coder message follows the error and differs from the mutated code; sandbox stderr text appears verbatim in the Coder's input; the following `exec_result` is ok; final `REVIEWER_APPROVED`; ≤12 messages; no human input.
- Demo A assertions: no injection event exists; the run completes or reports UNAPPROVED honestly; any natural error/repair is recorded as such.
- Each evidence folder holds `manifest.json` (model, version pins, mode, injected flag, counts, outcome), `events.jsonl`, `transcript.md`, `analysis.py`, artifacts and a usage summary. No secrets.
- Live tests assert behaviours, not exact wording.

Requirement ↔ test mapping lives in §10.

---

## 9. DEPLOYMENT

### 9.1 Artifacts
`Dockerfile` (app, py3.11-slim, non-root, healthcheck `/_stcore/health`), `docker-compose.yml` (app + labels; broker is a host service, see D11), `.env.example`, `.dockerignore`, `sandbox_service/` (broker + execution image recipe), `docs/DEPLOY.md`.

### 9.2 Traefik (placeholders until inspected — D7)
```yaml
labels:
  - traefik.enable=true
  - traefik.docker.network=<existing-traefik-network>
  - traefik.http.routers.datapilot.rule=Host(`<domain>`)
  - traefik.http.routers.datapilot.entrypoints=<websecure>
  - traefik.http.routers.datapilot.tls.certresolver=<existing-resolver>
  - traefik.http.services.datapilot.loadbalancer.server.port=8501
```
No edits to existing Traefik config or other stacks. Only add this service's labels/network membership.

### 9.3 Verification checklist
`docker compose config` · image build · container healthy · HTTPS cert valid · Streamlit WebSocket live run end-to-end · broker reachable only via socket · sandbox network none verified from inside an execution · no secrets in logs/image layers · other VPS apps unaffected · rollback rehearsed (`IMAGE_TAG=<prev> docker compose up -d`; remove labels to unpublish; broker unit stop).

---

## 10. TRACEABILITY (requirement → implementation → test → milestone)

| Req | Implementation | Test | M |
|---|---|---|---|
| §3.1 non-programmer user | Ask & Explore, plain answer | UX review | M2/M5 |
| §3.2 Planner | `agents/participants.py`, prompts | `test_planner_plan_contains_steps` | M3 |
| §3.2 Coder | same + repair prompts | `test_coder_receives_stderr`, live autofix | M3 |
| §3.2 Executor in sandbox | `sandbox/executor.py` + broker | `tests/sandbox/*` | M3 |
| §3.2 Reviewer | prompts + approval guard | `test_reviewer_only_approval`, `test_not_approved_ignored` | M3 |
| §3.2 User Proxy | `agents/human.py` | `test_human_stage_*` | M5 |
| §3.2 any CSV | `ingestion/*`, 2 schemas | `test_alt_schema_accuracy` | M2 |
| §3.2 watch conversation | Livewire + timeline | `test_event_mapping`, replay | M4 |
| §3.2 answer + PNG + py | `reports/*` | `test_artifacts_present` | M5 |
| §3.2 12 / APPROVED | `agents/termination.py` | `T-TERM-1..5`, boundary approval on message 12 | M3 |
| §3.3 loops | `agents/routing.py` | `test_exec_error_routes_to_coder`, `test_review_feedback_routes_to_coder` | M3 |
| §3.4 stack concepts | `agents/*` | code review | M3 |
| §3.5 sample input | `fixtures/` | accuracy eval | M2 |
| §3.6 conversation trail | events + Behind the Scenes | `test_behind_the_scenes` | M4 |
| §3.6B final answer | Insights narrative from `results.json` | `test_answer_numbers_in_results` | M5 |
| DC#1 auto-fix | Demo B (labelled fault injection) + any natural repair in Demo A | `-m live -k fault_injection`, `-k normal_run` | M3 |
| DC#2 sandbox only | broker, no in-process exec | `test_no_inprocess_exec`, sandbox suite | M3 |
| DC#3 never loops forever | `RunTerminator` | `T-TERM-1..5`, §3.3 table tests, timeout test | M3 |
| DC#4 same numbers | script export | `test_rerun_identical_hash` | M5 |
| DC#5 chart labels/units | validator + Reviewer | `test_chart_metadata` | M5 |
| DC#6 human approval + follow-up | UserProxy + session | `test_followup_same_session` | M5 |
| Stretch 1 Selector | `agents/teams.py` | `test_selector_guard`, live selector | M3 |
| Stretch 2 multi-sheet | ingestion + UI | `test_multisheet_end_to_end` | M5 |
| Stretch 3 one-page PDF | `reports/pdf.py` | `test_pdf_single_page` | M5 |
| `gpt-6-luna` | `config.py`, client, `scripts/check_model.py` | M2 step-0 model check | **M2** |
| Power BI UI | approved mockups → `ui/*` | mockup approval gate, screenshots vs mockups, review | M2/M6 |
| Livewire real events | `events/*`, `ui/livewire` | replay + no-sim audit | M4 |
| Sandbox isolation | §6 | §6.6 | M3 |
| Docker/Traefik/VPS | §9 | checklist | M7 |

---

## 11. RISKS

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | `gpt-6-luna` unavailable / unusual API | M | H | M2 step-0 check; stop and ask; configurable id; no substitution |
| R2 | AutoGen in maintenance mode; API drift | M | M | pin; record; adapter layer `agents/client.py`/`teams.py`; no Agent Framework migration without approval |
| R3 | Rootless Podman infeasible on VPS | M | H | feasibility checklist; fallbacks §6.1 need approval |
| R4 | Broker is a new attack surface | M | H | minimal API, no arbitrary flags/images, tests, reviewed |
| R5 | 12-message cap tight in RoundRobin (fixed P→C→E→R cycle ⇒ only three loops; two exec errors + one feedback round fails) | H | M | guarded selector default; §3.3 tests; honest UNAPPROVED outcome |
| R6 | Streamlit rerun/flicker | M | M | spike U5; reducer model; fallback placeholders |
| R7 | LLM nondeterminism makes live tests flaky | H | M | scripted tests are the gate; live tests assert behaviours, not wording |
| R8 | Reviewer rubber-stamps | M | H | pre-checks (static validators, number-in-results check) before Reviewer; approval guard |
| R9 | Cost/latency | M | L | token budget, caching, compact profile |
| R10 | Windows local python 3.14 default | H | L | explicit 3.11 venv; setup check |
| R11 | Visual shell built before design agreement ⇒ rework | M | M | M2 mockup approval gate |
| R12 | Fault injection mistaken for natural errors | L | H | separate demos, labels, manifest flag, UI badge |

---

## 12. DECISIONS REGISTER

| ID | Decision | Status |
|---|---|---|
| D1 | `gpt-6-luna` availability, `model_info`, price | planning assumption; **verified in M2 step 0** (stop and report if unavailable; no substitution) |
| D2 | AutoGen pin | planning assumption; confirm at M2 |
| **D3** | **Sandbox: L3 per-execution container; rootless Podman broker preferred** | **Approved target; feasibility checks §6.3 pending** |
| D4 | RoundRobin baseline + guarded Selector (UI default); budget per §3.3 | planning assumption |
| D5 | Thread + EventStore + `st.fragment(run_every)` | planning assumption; spike M4 |
| D6 | `results.json` contract | planning assumption |
| D7 | Traefik/VPS facts | read-only inspection, then approval |
| D8 | Explicit 3.11 venv | planning assumption |
| **D9** | Each follow-up starts a **new run with a fresh 12-message budget**, preserving session context (dataset, prior question/answer summaries) | **Approved** |
| **D10** | Retain Microsoft AutoGen (assignment requirement) despite maintenance mode | **Approved** |
| **D11** | Host-level broker with Unix-socket API (not Podman-in-Docker) | **Conditional** — subject to §6.3 feasibility **and** explicit deployment approval |
| **D12** | New dependencies `httpx`, Playwright, `pytest-asyncio`, `pydantic-settings` | **Approved**, with pinned versions and the justifications in §2.1 |

## 13. NEXT STEP

After user review of this PRP: `/execute-prp PRPs/datapilot-prp.md --milestone M2`

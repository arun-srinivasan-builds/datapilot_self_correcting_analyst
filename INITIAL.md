# INITIAL.md — DataPilot: Self-Correcting Data Analyst

> Product definition for `/generate-prp INITIAL.md`.
> **Authoritative source:** `docs/SocialEagle_UseCase_Definitions.pdf`, Use Case 03, pp. 9–11, sections 3.1–3.8 + Done Checklist + stretch goals.
> Everything below supplements the PDF. Where this file and the PDF appear to disagree, see **§16 Conflicts & Resolutions**.

---

## 1. PRODUCT

| | |
|---|---|
| **Name** | DataPilot — Self-Correcting Data Analyst |
| **Context** | Social Eagle AI Academy, Agentic AI track, Assignment 03 (AutoGen). Intermediate, "3 days". |
| **Type** | Learning assignment. **Not** a customer SaaS product. |
| **One line** | Ask a business question in plain English; a team of AutoGen agents plans, writes Python, runs it in a sandbox, fixes its own errors, and returns a verified answer with charts. |
| **Contrast with Assignment 02** | LaunchScout (CrewAI) ran a fixed task order. DataPilot's agents decide the path at runtime: errors go back to the Coder, Reviewer dissatisfaction goes back to the Coder, until approval or a hard limit. |

**Primary acceptance criterion:** the application genuinely corrects its own code with no human debugging. A fixed pipeline, simulated correction, scripted conversation, or hardcoded answer is a failure.

---

## 2. PROBLEM AND USERS (PDF §3.1)

A business owner, sales manager or operations head has sales data (CSV/Excel) but cannot write Python or SQL. A normal chatbot guesses numbers. DataPilot **calculates** them by writing and executing real code on the uploaded data, and checks its own work.

Reference question: *"Which category had the biggest revenue drop in September vs August, and which region caused most of it?"*

DataPilot must: understand the question → inspect the data → plan → generate Python → execute on actual data → detect and repair errors → verify → present a concise, trustworthy answer with charts and reproducible code. The user needs no programming knowledge.

---

## 3. TECH STACK (approved; no additions without approval)

| Component | Choice |
|---|---|
| Runtime | Python **3.11** everywhere (venv, Docker, CI, ruff `target-version = "py311"`) |
| Agent framework | Microsoft AutoGen, **modern AgentChat API** (`autogen-agentchat` + `autogen-ext[openai]`; pinned) |
| LLM | `OPENAI_MODEL=gpt-6-luna` via `OPENAI_API_KEY` (env only; see §3.1) |
| UI | Streamlit |
| Data | pandas, openpyxl |
| Charts | matplotlib (PNG exports, `Agg` backend); Plotly for interactive views in the UI |
| PDF | ReportLab |
| Tests / lint | pytest, Ruff |
| Packaging | Docker, Docker Compose |
| Code execution | Isolated Docker sandbox (separate service; see §10) |
| Proxy / host | Traefik on the existing Hostinger VPS |

**Not used:** React, Next.js, FastAPI, PostgreSQL, JWT, OAuth, subscriptions, billing. No database unless a justified dependency emerges (then document and request approval).

### 3.1 Model configuration rules
1. `OPENAI_API_KEY` and `OPENAI_MODEL` come from environment only. Model id lives in one config module.
2. Verify real availability/API compatibility in M3 with a minimal live call. **Never silently substitute a model**; if unavailable, report and ask.
3. A model name unknown to AutoGen needs an explicit `model_info` (function calling, vision, json output, family) on the client — verify against the pinned version.
4. Track token usage per agent/run; cost estimate uses a **configurable price table** (price for this model is not assumed).
5. No duplicate/unnecessary LLM calls (cache planner context per dataset; one Reviewer call per execution result).

---

## 4. RUNTIME AGENTS — AutoGen participants (PDF §3.2)

> These are *product* agents. They are unrelated to the Claude Code *development* agents in `agents/`.

| Agent | AutoGen type (verify in M3) | Responsibility |
|---|---|---|
| **Planner** | `AssistantAgent` | Reads question + dataset profile (columns, dtypes, metadata); writes a short step-by-step plan: calculations, groupings, comparisons, charts. |
| **Coder** | `AssistantAgent` | Writes pandas + matplotlib code for the plan; receives real Executor errors and repairs; incorporates Reviewer feedback; produces final `analysis.py`. |
| **Executor** | `CodeExecutorAgent` + custom sandbox `CodeExecutor` | Runs code **only** in the sandbox service; returns real status, stdout, stderr, artifacts. Never runs code in the Streamlit process. |
| **Reviewer** | `AssistantAgent` | Does it answer the question? numbers sensible/consistent? charts titled, axes labelled, units shown? outputs match executed code? Replies `APPROVED` only when satisfied, else actionable feedback. |
| **User Proxy** | `UserProxyAgent` (post-loop) | Human approval stage: approve/reject final answer, ask follow-ups in same session. Human stays in control of final acceptance. |

Reviewer approval ≠ human approval. They are separate states in the UI and logs.

---

## 5. AUTONOMOUS WORKFLOW (PDF §3.3)

`ASK → PLAN → CODE → EXECUTE → REVIEW → ANSWER`

**Execution-error loop:** Executor error → actual error returned to Coder → corrected code → Executor reruns → repeat within the message limit. No human debugging.

**Reviewer-feedback loop:** code runs but Reviewer is unsatisfied → specific feedback to Coder → revised code → Executor → Reviewer → repeat.

### Termination (mandatory)
- Stop when the **Reviewer** issues `APPROVED`. `APPROVED` from any other participant, or quoted inside code/data/stdout, must **not** terminate.
- Otherwise stop after **12 agent messages** total. An *agent message* is one chat message from Planner, Coder, Executor or Reviewer; the task message, agent events and human-stage messages are not counted (`PRPs/datapilot-prp.md §3.2`). Corrections count in the same budget; the counter never resets within a run. Approval on the 12th message is valid. Each follow-up question is a new run with a fresh budget (D9).
- Hitting the limit shows an **UNAPPROVED / INCOMPLETE** outcome. An unapproved analysis is never presented as verified.
- Reviewer may not approve if the latest Executor result was an error (guardrail).
- No infinite loops under any path.

### Orchestration
- `RoundRobinGroupChat` = assignment baseline.
- `SelectorGroupChat` = Stretch Goal 1 (LLM-picked next speaker), with a deterministic override so an Executor failure always routes to Coder.
- Termination via AutoGen conditions: Reviewer-sourced `APPROVED` **OR** `MaxMessageTermination(12)` (see §16 for semantic checks on what the library counts).

---

## 6. DATASET INGESTION (PDF §3.2, §3.5 + Stretch 2)

- CSV and `.xlsx` upload; **multi-sheet workbooks with sheet selection** (Stretch 2).
- Preview, column names and dtypes, row count, missing-value indicators, date-column detection, basic data-quality validation.
- **Schema-agnostic:** the PDF sample (`order_date, region, category, product, units, unit_price, discount`) is a test fixture, never the only accepted schema. Derived metrics (e.g. revenue) are the agents' job, not hardcoded.
- Numbers come from executed Python, never LLM guesses.
- Dataset content is **untrusted** (prompt-injection surface; see §12).

---

## 7. OUTPUTS (PDF §3.6–3.7)

Every **approved** analysis provides:

1. Plain-English answer (concise, business language)
2. Exact calculated values
3. Contributing factors (e.g. region/product breakdown)
4. PNG charts — **title, axis labels, units on every chart**
5. Downloadable `analysis.py`; 6. downloadable PNGs
7. **One-page PDF** report (answer + charts) (Stretch 3)
8. Real agent conversation + correction history
9. Reviewer approval status; 10. human approval controls
11. Follow-up question in the same session; suggested next question

**Reproducibility:** re-running saved `analysis.py` on the same dataset yields identical numbers (deterministic: no wall-clock, no unseeded randomness, stable sort order, dataset path passed as argument/relative).

Currency/units are inferred from data/question; `₹ / L` in the PDF sample is an example, not a constant.

---

## 8. UI — Power BI-inspired "Intelligence Studio" (critical)

Streamlit is the **framework**, not the visual reference. Forbidden: stacks of Streamlit cards/`st.container()` sections, repetitive rounded KPI boxes, chatbot-with-charts-below, disconnected default sidebar controls, SaaS landing page, decorative dashboards with no analytic purpose.

**Identity:** deep midnight navy; graphite/slate surfaces; restrained electric teal + blue accents; ivory text; compact analytical controls; minimal borders and rounding; integrated report canvases; strong hierarchy; WCAG-AA contrast. Do not copy Power BI branding/assets.

### Workspace 1 — Ask & Explore
Dataset upload; CSV/Excel + sheet selection; profiling; preview; column and quality indicators; question composer; suggested questions; session conversation history. The user must know how to begin immediately.

### Workspace 2 — Agent Livewire (signature feature)
Large live orchestration/observability canvas showing: Planner, Coder, Executor, Reviewer, human approval stage; real messages; transitions; code generation; execution results; errors; automatic repairs; reviewer feedback; approval/termination; **live message count / 12**. Not four static cards with arrows.

### Workspace 3 — Insights Studio
Compact KPI strip; coordinated charts; relevant filters; interactive tables; drill-down where appropriate; narrative insights; reviewer verification status; human approval controls; downloads (py/PNG/PDF); follow-up composer. Reads as one report canvas.

### Responsiveness / quality
Desktop, laptop, tablet, mobile. No horizontal overflow, overlap, clipped labels, chart truncation, or oversized empty space. Accessible contrast, keyboard access where practical, `prefers-reduced-motion` support. Automated viewport tests + human-reviewed screenshots; UI is not "done" because it runs.

---

## 9. LIVEWIRE — real-event animation (mandatory)

The animation reflects **real AutoGen runtime events** only.

Must: highlight active agent; pulse while executing; animate a connection when a real message transfers; stream messages as they arrive; show code-execution events and errors; animate Executor→Coder repair and Reviewer→Coder feedback routes; show revise/re-execute; live counter; Reviewer approval; human approval separately; 12-message termination; expandable event timeline; inspect generated code, stdout, stderr, reviewer feedback.

Prohibited: simulated messages, fake progress %, scripted flows shown as live, artificial delays, hardcoded "correction demos" shown as live, fabricated reasoning. Never show hidden chain-of-thought — only observable messages, tool/exec events, guardrail outcomes, results.

A *deterministic fault-injection test* may deliberately produce a first-run error, but the repair must come from the real Coder.

**Engineering note:** AutoGen is async-streaming; Streamlit reruns top-to-bottom. M4 must prototype and choose a bridge (see §15 D5). Target: no flicker, no duplicate model calls on rerun.

---

## 10. SECURE SANDBOX

Generated Python runs in an isolated Docker environment separate from Streamlit.

Requirements: separate container; **no host Docker socket in the Streamlit app**; no Docker-in-Docker or privileged mode without explicit approval; no unrestricted host FS; no network by default; CPU/memory/PID limits; execution timeout; read-only dataset mount; per-session working dir; controlled artifact output dir with safe path handling (no traversal/symlink escape); no `OPENAI_API_KEY` or VPS secrets in the sandbox; temp cleanup; structured execution logs.

**Isolation levels (full analysis in `skills/SANDBOX.md`):**
- **L2 — long-running sandbox service**, runs as subprocesses with rlimits, per-run directories and a minimal environment, on an `internal: true` network. This is **not** equivalent to a fresh isolated container per execution: runs share one container's namespaces and service process.
- **L3 — fresh ephemeral container per execution** via a narrowly scoped broker (rootless Podman or a filtered Docker-API proxy), network none, destroyed after each run. Stronger; needs VPS compatibility checks and approval.
- **L4 — gVisor/Kata/microVM**: strongest, likely out of scope.

**Decision D3 (approved):** L3 is the target; the executor sits behind a swappable `CodeExecutor`/broker interface so fallbacks need no agent changes. Feasibility is investigated read-only during M3/M7. L2's limitations (shared namespaces, surviving child processes, leftover state, same-container service) must be stated in the PRP, README and completion report. The PDF permits "Docker or local folder"; a local folder is **not** acceptable here (stricter requirement).

---

## 11. DOCKER / TRAEFIK / VPS

Python 3.11 images; Streamlit app container; isolated sandbox container; Docker Compose; env config; healthchecks; persistent artifact volume where needed; Traefik routing with HTTPS via existing cert infrastructure; Streamlit WebSocket (`/_stcore/stream`) compatibility; safe coexistence with other VPS apps; deployment verification; rollback notes.

**Do not touch the VPS or Traefik config before inspecting it and getting approval.** (Network name, entrypoints, cert resolver, domain: unknown — see §15 D7.)

---

## 12. GUARDRAILS, EVALUATIONS, OBSERVABILITY

- File validation (type, size, extension vs content, zip-bomb/macro-safe handling for xlsx)
- Dataset schema validation and bounds (rows/cols)
- Prompt-injection resistance: cell/column text is delimited as data; agents instructed that data never carries instructions; Reviewer checks code for network/FS/exec misuse; sandbox is the real boundary
- Message limit, timeout, Reviewer-only approval verification
- Numerical-accuracy evals against pandas ground truth; reproducibility re-run check; artifact validation (PNG exists, labelled; PDF 1 page)
- Token/cost tracking; structured JSON logs; secrets never logged
- **Behind the Scenes** panel: agent messages, executor activity, errors, code corrections, reviewer feedback, guardrail outcomes, eval results, termination reason, token usage. No secrets, no chain-of-thought.

---

## 13. TESTING (pytest + Ruff)

Deterministic tests use **mocked LLM** (scripted model client). Live-model tests are marked `@pytest.mark.live` and excluded by default.

Cover: CSV upload; Excel upload; multi-sheet; profiling; Planner output; Coder generation; Executor operation; **autonomous error repair**; Reviewer rejection→correction; Reviewer-only approval; 12-message termination; human approval; same-session follow-up; numerical accuracy; chart labels/units; reproducible script; PDF generation; **event→animation mapping**; sandbox isolation (no network, no secrets, no escape); resource limits; API efficiency (call counts); responsive UI (Playwright viewports + screenshots); Docker deployment smoke.

**At least one real end-to-end run** must show an execution error fixed automatically by the live agents.

---

## 14. REQUIREMENTS TRACEABILITY

| Req | Source | Implementation (planned) | Milestone | Verified by |
|---|---|---|---|---|
| Real problem; non-programmer user | PDF §3.1 | §2; Ask & Explore workspace; plain-English answer | M2/M5 | UX review |
| Planner | §3.2 | `AssistantAgent`, profile-aware prompt | M3 | unit (mock LLM) |
| Coder | §3.2 | `AssistantAgent`, pandas+matplotlib, repairs from errors | M3 | unit + e2e |
| Executor in sandbox | §3.2, DC#2 | `CodeExecutorAgent` + sandbox-service executor | M3 | isolation tests |
| Reviewer APPROVED/feedback | §3.2 | `AssistantAgent`; Reviewer-sourced termination | M3 | unit |
| User Proxy approval + follow-up | §3.2, DC#6 | post-loop `UserProxyAgent`/approval stage; same session state | M5 | unit + UI |
| Upload any sales CSV | §3.2 | ingestion module, schema-agnostic | M2 | fixtures (≥2 schemas) |
| Watch conversation incl. errors/fixes | §3.2, §3.6A | Livewire + timeline | M4 | event mapping tests |
| Answer + PNG + analysis.py | §3.2, §3.6B | outputs §7 | M5 | artifact tests |
| Safety: 12 msgs or APPROVED | §3.2, DC#3 | termination §5 | M3 | termination tests |
| ASK→PLAN→CODE→RUN→REVIEW→ANSWER loop | §3.3 | RoundRobin baseline | M3 | e2e |
| Error→Coder, Reviewer→Coder loops | §3.3 | routing guard §16-C2 | M3 | scripted-LLM tests |
| AssistantAgent/CodeExecutorAgent/RoundRobin/Termination/UserProxy/pandas+mpl | §3.4 | stack §3 | M3 | code review |
| Sample input (12,480 rows) | §3.5 | fixture generator + question | M2/M6 | accuracy eval |
| Conversation trail shown | §3.6A/§3.7 | Behind the Scenes + Livewire | M4 | UI test |
| Final answer w/ exact numbers + cause + next question | §3.6B | Insights Studio narrative | M5 | accuracy eval |
| DC#1 auto-fix run | §3.8 | e2e fault-injection | M3/M6 | e2e log |
| DC#2 sandbox only | §3.8 | §10 | M3 | isolation tests |
| DC#3 never loops forever | §3.8 | §5 | M3 | termination tests |
| DC#4 identical re-run numbers | §3.8 | determinism + rerun check | M5 | repro test |
| DC#5 chart title/axes/units | §3.8 | Reviewer + static label validator | M5 | artifact tests |
| DC#6 human approval + follow-up | §3.8 | §4 User Proxy | M5 | session test |
| **Stretch 1** SelectorGroupChat | §3.8 | mode switch with routing guard | M3 | routing tests |
| **Stretch 2** multi-sheet Excel | §3.8 | §6 | M2/M5 | fixture test |
| **Stretch 3** one-page PDF | §3.8 | ReportLab | M5 | PDF page-count test |
| Supplement: gpt-6-luna | prompt | §3.1 | M3 | live smoke |
| Supplement: Power BI-style UI, Livewire | prompt | §8–9 | M2/M4/M6 | screenshot review |
| Supplement: sandbox, guardrails, evals | prompt | §10, §12 | M3/M6 | tests |
| Supplement: Docker/Traefik/VPS | prompt | §11 | M7 | deploy verification |

---

## 15. MILESTONES

| # | Name | Gate |
|---|---|---|
| M1 | Requirements & template adaptation (this) | docs consistent; review approved |
| M2 | Foundation & premium UI shell | model check passed; py3.11 env; ingestion; **approved UI mockups before any visual shell**; lint/tests pass |
| M3 | Real AutoGen execution engine | Demo A normal run + Demo B labelled fault-injection repair; termination tests; sandbox isolation tests |
| M4 | Live Agent Livewire | real-event animation; timeline; no flicker |
| M5 | Insights & stretch goals | PNG/analysis.py/PDF; multi-sheet; approval; follow-up; repro |
| M6 | Quality & validation | guardrails/evals; responsive screenshots; API efficiency |
| M7 | Docker, VPS & closure | HTTPS deploy verified; rollback doc; completion report |

Track start/end clock time and rework cycles per milestone in `docs/MILESTONES.md`. Exclude personal breaks.

### Open decisions (recommendations)

| ID | Decision | Recommendation |
|---|---|---|
| D1 | Model availability / `model_info` / pricing for `gpt-6-luna` | One minimal live compatibility check as the **first action of M2**; stop and report if unavailable; never substitute |
| D2 | AutoGen exact version pin | Pin the latest stable `autogen-agentchat`/`autogen-ext` pair at M2 (version unverified today); record API deltas in `skills/AUTOGEN.md` |
| D3 | Sandbox isolation level | **Approved: L3 per-execution container is the target, preferably via a rootless Podman broker.** Feasibility on the VPS is unverified; L3-d (Docker runtime behind the broker) or L2 are fallbacks needing explicit approval. No Podman install or VPS change without approval. See `PRPs/datapilot-prp.md §6` |
| D4 | RoundRobin vs error routing (§16-C2) | Baseline RoundRobin with Reviewer relaying errors tersely; guarded mode via `SelectorGroupChat(selector_func=…)` |
| D5 | Streamlit↔AutoGen bridge | Background worker thread + thread-safe event queue; UI polls via `st.fragment(run_every=…)`; SVG/CSS-driven animation. Spike in M4; fallback `st.empty()` placeholder |
| D6 | Structured results channel | Coder also writes `results.json` (tables, KPIs) so Insights Studio renders Plotly/KPIs from verified data, not LLM prose |
| D7 | Traefik/VPS facts (network, entrypoint, resolver, domain) | Read-only inspect in M7, then ask approval |
| D8 | Local Python | `python` on PATH resolves to 3.14 first; use explicit 3.11 venv (`py -3.11`) |

---

## 16. CONFLICTS & RESOLUTIONS

| ID | Conflict | Resolution |
|---|---|---|
| C1 | PDF: `TextMentionTermination('APPROVED')` fires on any speaker; supplement: Reviewer-only. | Restrict to Reviewer source (if the pinned version supports `sources`, else a custom termination). Require exact standalone token; refuse approval after failed execution. |
| C2 | Round-robin order is fixed (…Executor→Reviewer); supplement: failures must return to Coder, not advance to Reviewer. PDF §3.6 shows Executor ERROR → Coder directly. | Guarded routing via `SelectorGroupChat` selector function (Executor error ⇒ Coder). In pure RoundRobin the cycle is fixed (P→C→E→R→P…): each error costs a Reviewer relay and each loop a Planner turn, so only three loops fit in 12 (`PRPs/datapilot-prp.md §3.3`). Decision D4. |
| C3 | PDF puts User Proxy in the team; a team `UserProxyAgent` blocks on input each cycle and fights the autonomous 12-message loop. | User Proxy acts as the post-`APPROVED`/limit approval stage and follow-up entry; autonomous loop stays human-free. |
| C4 | `MaxMessageTermination(12)` may count the initial task and non-chat events; supplement says "12 agent messages". | Verify counting semantics in M3 and encode explicit definition + tests; document. |
| C5 | PDF: "Streamlit chat"; supplement: not a generic chatbot. | Composer + conversation history inside the BI workspace; chat is not the layout. |
| C6 | PDF: sandbox may be "local folder"; supplement: Docker isolation, no socket, no DinD. | Docker-based sandbox (L2 now, L3 preferred; D3). Stricter wins; L2 is never described as per-run containers. |
| C7 | PDF example uses ₹/L. | Units inferred from data; not hardcoded. |
| C8 | Template CLAUDE.md: "no inline styles". Custom BI UI requires CSS. | Styles live in one theme module/CSS file; no scattered inline styles. |
| C9 | Template workflow `/execute-prp` expects web stack and `PRPs/`. | Rewritten for DataPilot (M1). |

---

## 17. ACCEPTANCE CRITERIA

**PDF Done Checklist**
- [ ] At least one run shows agents fixing a code error on their own
- [ ] Code runs only inside the sandbox
- [ ] Stops on `APPROVED` or after 12 messages, never loops forever
- [ ] Re-running saved `analysis.py` gives exactly the same numbers
- [ ] Every chart has title, axis labels and units
- [ ] Human approval works; follow-up continues the same session

**Stretch**
- [ ] SelectorGroupChat mode  - [ ] Multi-sheet Excel  - [ ] One-page PDF

**Supplement**
- [ ] Reviewer-feedback loop demonstrated; Reviewer-only approval enforced
- [ ] Livewire driven by real events; timeline + inspection
- [ ] Power BI-style three workspaces; responsive; reduced-motion; visually reviewed
- [ ] Sandbox isolation tests pass; no secrets in sandbox
- [ ] `ruff check` and `pytest` pass (live tests separate); Python 3.11 throughout
- [ ] Docker build; HTTPS via Traefik; deployment verified; rollback documented

---

## 18. RUN

```
/generate-prp INITIAL.md          # after M1 review approval
/execute-prp PRPs/datapilot-prp.md
```

Milestone 1 stops before PRP generation.

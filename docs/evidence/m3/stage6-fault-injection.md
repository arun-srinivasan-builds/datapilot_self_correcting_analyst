# M3 Stage 6: controlled fault injection

Date: 2026-10-16 · Scope: Stage 6 only · **Model: scripted replay (no live OpenAI call).**
**Sandbox: real Docker containers through the real broker.** The only synthetic act is the labelled,
test-only mutation of the Coder's code message. The error, the stderr, the re-execution and every
event after the mutation are genuine.
Raw evidence: `docs/evidence/m3/stage6/<scenario>/` (`events.jsonl`, `summary.json`,
`fault-record.json`, `1-original-coder-output.py`, `2-executed-after-injection.py`,
`3-corrected-and-executed.py`, `injection.diff`), `full-regression.txt`, `stall-diagnostics.txt`.

## 1. Design
| Piece | What it does |
|---|---|
| `datapilot/faults.py` | `FaultSpec` (deterministic find/replace on the Coder's single python block), `FaultInjector`, `FaultRecord` (original + mutated message/code, hashes, diff), `authorize()` |
| `FaultInjectingCoder` (`agents/participants.py`) | Subclass of `AssistantAgent`. Intercepts the Coder's `Response`, mutates it, **and rewrites the assistant message AutoGen already stored in the Coder's own model context**, then verifies the rewrite (length and last message). Any mismatch raises `FaultInjectionError` and the run ends as `ERROR` (never hidden) |
| Events | `test_fault_injected` (source `test_harness`, payload `test_only: true`, fault name, original/mutated hash) is emitted **before** the faulty `code_generated`; `code_generated`, `exec_started`, `exec_result` of the injected code carry `injected_fault`; the genuine correction does not |
| Faults | `missing_column` (`df["units"]` -> `df["qty"]`, raises `KeyError`), `hang` (endless loop after the imports) |
| Wiring | `RunConfig.fault` (default `None`; `from_settings` never sets it) -> `build_team` attaches the injector to the run's store/state. `run_question` has no fault parameter |

### Guardrails (all tested)
- **Disabled by default:** `APP_ENV=production` and `FAULT_INJECTION=""` by default; `RunConfig().fault is None`.
- **Explicit test/diagnostic mode only:** `authorize()` requires `APP_ENV in {test, diagnostic}` **and** `FAULT_INJECTION` naming that fault. `FaultInjector` cannot be constructed directly (private token) and is limited to 1-8 injections.
- **Cannot escape the boundary:** production settings refuse even with `FAULT_INJECTION` set (and `RunConfig.from_settings` ignores it); unknown fault / unknown `APP_ENV` are refused; no module under `datapilot/ui` references `datapilot.faults` (static scan) and importing the whole UI does not load it (subprocess check). The test suite clears `APP_ENV`/`FAULT_INJECTION` from the environment so neither can leak in.
- **No silent no-op or silent change:** a fault whose pattern is absent raises (`not-applicable` scenario: run ends `ERROR`, nothing executed); a no-op mutation is refused; unusable Coder replies (no/multiple blocks) are left alone and do not consume an injection.
- **No fabrication:** no messages, tool calls or results are added; the 12-message cap, token budget, timeouts, approval rules and human-approval separation are untouched and proven below.

### AutoGen limitation and how it is handled (not hidden)
AutoGen 0.7.5 has no supported API to replace an agent's own previous reply in its memory. The injection relies on (a) the private attribute `AssistantAgent._model_context` and (b) `ChatCompletionContext.clear()/add_message()`. It works for the plain-text path (no tools / reflection) used here. It is guarded: the history is copied before the rewrite (a unit test caught that some contexts return their internal list, which would have made the check vacuous), and the rewrite is verified; a context that cannot be rewritten makes the run fail loudly (`test_stage6_injected_message_replaces_the_coders_own_memory`). A future AutoGen upgrade must keep the Stage 6 tests green; this dependency on a private attribute is a maintenance risk (R-AG1).

## 2. Before and after (actual code from `injected-repair`)
```diff
--- original (Coder's own output)            hash 932b0bb16496
+++ executed (after test-only mutation)      hash e139383e2bbc
@@ -5,7 +5,7 @@
 df = pd.read_csv(os.environ["DATA_PATH"], parse_dates=["order_date"])
-df["revenue"] = df["units"] * df["unit_price"] * (1 - df["discount"])
+df["revenue"] = df["qty"] * df["unit_price"] * (1 - df["discount"])
```
The correction (scripted second Coder reply) executed in a second container has hash `932b0bb16496`
(the original), which differs from the executed mutation `e139383e2bbc`. The repair is *scripted*; proving that the
real `gpt-6-luna` derives such a fix from the stderr is Stage 9.

## 3. Actual execution trace (`stage6/injected-repair/events.jsonl`)
```
 1 run_started         app
 2 speaker_selected    selector     next=Planner (start)
 3 usage               Planner      in=367 out=31
 4 agent_message       Planner      Plan: 5 steps
 5 speaker_selected    selector     next=Coder (plan_done)
 6 usage               Coder        in=530 out=148
 7 test_fault_injected test_harness fault=missing_column original=932b0bb16496 mutated=e139383e2bbc TEST ONLY
 8 code_generated      Coder        v1 hash=e139383e2bbc injected_fault=missing_column
 9 agent_message       Coder        analysis.py v1 · 33 lines
10 speaker_selected    selector     next=Executor (code_ready)
11 exec_started        Executor     code_hash=e139383e2bbc injected_fault=missing_column
12 exec_result         Executor     status=error exit=1 stderr_last='KeyError: 'qty'' injected_fault=missing_column
13 agent_message       Executor     error · exit 1
14 repair_routed       selector     attempt=1
15 speaker_selected    selector     next=Coder (exec_failed)          <- guarded selector: failure -> Coder, never Reviewer
16 usage               Coder        in=797 out=148                    <- Coder's input contains the real stderr and the EXECUTED code
17 code_generated      Coder        v2 hash=932b0bb16496
18 agent_message       Coder        analysis.py v2 · 33 lines
19 speaker_selected    selector     next=Executor (code_ready)
20 exec_started        Executor     code_hash=932b0bb16496            <- new sandbox execution (different broker exec id)
21 exec_result         Executor     status=ok exit=0
22 agent_message       Executor     ok · exit 0
23 speaker_selected    selector     next=Reviewer (exec_ok)
24 usage               Reviewer     in=897 out=13
25 agent_message       Reviewer     APPROVED
26 reviewer_approved   Reviewer     message=6
27 terminated          app          REVIEWER_APPROVED msgs=6
```
Identifiers preserved in `fault-record.json`: broker execution ids (`df668894…` for the injected run, `8a0c77e7…` for the correction), code hashes, event sequence numbers (fault event 7, execs 11/12 and 20/21), stderr tail, durations.

## 4. Scenarios (all passed; real containers)
| Scenario | Outcome | Order | Msgs | Injections | Executions |
|---|---|---|---|---|---|
| injected error -> repair | REVIEWER_APPROVED | PCECER | 6 | 1 | error/1 -> ok/0 |
| injection disabled (normal run) | REVIEWER_APPROVED | PCER | 4 | 0 | ok/0; executed code == Coder's code |
| named fault in production mode | `authorize()` refused; run unaffected (code unchanged, no fault event) | - | - | 0 | ok/0 |
| unusable reply skipped, next valid one faulted | REVIEWER_APPROVED | PCCECER | 7 | 1 | error -> ok |
| fault does not apply | **ERROR** (explicit) | P | 1 | 0 | none ran |
| 5 injected failures | **LIMIT_REACHED** (unapproved) | PCECECECECEC | 12 | 5 | 5 x error/1, Reviewer never called |
| round-robin, Reviewer says APPROVED after every failure | **LIMIT_REACHED** | PCERPCERPCER | 12 | 3 | 3 premature approvals ignored (guardrail), none counted |
| round-robin, approval after the repair | REVIEWER_APPROVED (msg 8) | PCERPCER | 8 | 1 | error -> ok |
| token budget (55%) | **TOKEN_BUDGET_EXHAUSTED** | PCE | 3 | 1 | error/1 |
| message cap 3 | **LIMIT_REACHED** | PCE | 3 | 1 | error/1 |
| hang -> sandbox timeout (10 s) -> repair | REVIEWER_APPROVED | PCECER | 6 | 1 | timeout/124 -> ok |
| hang -> run wall-clock timeout (6 s) | **TIMEOUT** | PC | 2 | 1 | cancelled: no result invented, container removed |
| hang -> user stop (6 s) | **STOPPED** | PC | 2 | 1 | cancelled, container removed |
| natural (non-injected) KeyError vs injected KeyError | both REVIEWER_APPROVED | PCECER | 6 | 0 / 1 | error -> ok |
| natural OOM, no fault object | REVIEWER_APPROVED | PCECER | 6 | 0 | killed/137 -> ok; not mislabelled |

### Final validation and approval rules (asserted)
- Final `results.json` of the repaired run equals the fixture ground truth (Electronics -3,980,399.85; South -5,596,984.50).
- `reviewer_approved` appears only after a successful execution (message 6 / 8), never after an unresolved failure; Reviewer `APPROVED` after a failed execution is ignored by the guard (and still counted).
- Reviewer approval stays separate from human approval (`human == none`, not fully verified).

### Coder-memory consistency (asserted on the Coder's real second model input)
Exactly one assistant message is in the Coder's history and it equals the mutated message; the input contains `df["qty"]`, not `df["units"]`, plus the container's stderr verbatim. The Reviewer's input also shows the executed (mutated) code and the real `KeyError: 'qty'`.

### EventStore and Livewire distinguish injected from natural failures
Events: `test_fault_injected` + `injected_fault` flags exist only in the injected run. The approved Livewire view-model (`build_canvas`, `feed_items`) shows `fault=True` and a `test_fault_injected ... (TEST ONLY)` feed line for the injected run and neither for the natural one. The UI itself was not modified.

## 5. Gates, tests, coverage
| Gate | Result |
|---|---|
| 3.11 guard / Ruff check + format / `pip check` | green / clean (96 files) / clean |
| **Full non-live regression** (unit + real-container sandbox + Stage 5 + Stage 6) | **372 passed**, 0 failed, 14 min 34 s (previous gate: 342) |
| Stage 6 tests | 29 (13 boundary, 16 real-container scenarios) + 1 no-Docker memory test |
| Coverage (`src/datapilot` + `sandbox_service`) | **94%** (3185 statements, 199 missed); `faults.py` 100%, `participants.py` 99%, `termination` 99%, `runner` 98%, `executor` 96%, `mapping` 99% |
| Cleanup | after the full run: 0 containers with the sandbox label, `.sandbox/` empty; every scenario was checked by the leak fixture; `test_zz_nothing_is_left_behind_by_any_scenario` |
Lint now excludes `docs/evidence` (generated code snapshots such as `2-executed-after-injection.py` are evidence, not source).

## 6. Findings
1. **Memory/response/execution consistency is achievable and verified**, but only through a private AutoGen attribute (see §1). The history-aliasing pitfall was caught by a unit test.
2. The earlier full-regression run in this stage failed one Stage 5 test (`..._execution_timeout_is_a_repairable_...`) after 130 s (run-level 120 s timeout hit): a fourth unexplained stall. It passed in the next full run and in an 18-iteration loop.
3. Total suite time grew from 9 to 14.5 min mainly because ~16 more real-container scenarios run; no stack dump fired in 39 armed scenarios.

## 7. Items kept OPEN (explicitly)
1. **Docker stall: still unexplained (4 observations).** Stage 6 added a stack dump (all threads, incl. broker handlers) if any scenario exceeds 45 s, plus per-phase broker timings. Reproduction attempt: 18 consecutive runs of the failing scenario, 18.4-26.0 s each, no stall; iterations 4-7 were uniformly slower in *every* phase (good-script run 7-9 s instead of ~5 s, create/remove up to 2x), consistent with transient host/VM contention but not proof. No stall occurred in the final full run (39 scenarios armed, none > 45 s).
2. **Streaming budget coverage:** `BudgetedClient.create_stream` remains untested (module coverage 78%); no streaming is used in M3.
3. **Real network cancellation:** the run timeout/stop were proven with scripted clients and real container cancellation only. Cancelling a hung real OpenAI HTTP call is unverified until live use (Stage 9).
4. Also still open: reasoning-token accounting (needs a live call), real-model behaviour of the repair cycle (scripted here), Docker Desktop is not security-equivalent to the proposed rootless-Podman VPS.

## 8. Not done (by instruction)
Stage 7 follow-ups, Stage 8 live UI wiring, UI changes, live model calls, VPS access, Podman, deployment, commits. `CLAUDE.md` was not edited; the new keys `APP_ENV` and `FAULT_INJECTION` are documented here and in `.env.example` only.

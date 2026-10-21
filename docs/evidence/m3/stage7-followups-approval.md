# M3 Stage 7: follow-ups and human approval

Date: 2026-10-16 · Scope: Stage 7 only · **Model: scripted replay (no live OpenAI call).**
**Sandbox: real Docker containers, real broker, real artifact store.** UI unchanged (Stage 8 wires it).
Raw evidence: `docs/evidence/m3/stage7/<scenario>/` (per-run `*-events.jsonl`, `runs.json`, `audit.json`),
`full-regression.txt`, `stage7/host-standby-intervals.csv`, `stage7/host-power-final-run.txt`.

## 1. Design (what was built)
| Piece | Behaviour |
|---|---|
| `datapilot/session.py` `Session` | One dataset (validated and profiled once; fixed bytes + SHA-256), many runs. `ask()` always creates a **new run**: new `run_id`, new `EventStore`, new team and `RunState` (via `run_to_report`), so the 12-message counter, token budget and wall-clock timer start fresh. One active run at a time (`SessionBusy`) |
| `RunRecord` | Per-run identity: run_id, sequence, parent run, context run ids, outcome, messages, tokens, `usage_by_source`, broker exec ids, code hashes; for Reviewer-approved runs also verified facts, artifact identities (name, size, sha256, broker exec id) and an artifact digest |
| Context rule | Only runs that are **Reviewer-approved with a valid results contract and no reducer violations**, and not human-rejected, are trusted. At most the latest 3. Each contributes **only** sanitized facts (label/value/unit, control characters removed, length-bounded), artifact names + hashes, the question and a status label (`reviewer_approved` / `reviewer_approved+human_approved`). Never code, stdout, stderr, agent messages, exec ids or instructions. Failed, limited, timed-out, stopped, token-exhausted, errored and rejected runs contribute nothing. Context enters the task inside the existing `UNTRUSTED_DATA` block |
| Human stage | `Session.approve()` / `reject()` are the only code paths that create human events (`source=human`). Nothing approves automatically |
| Approval preconditions | run exists and is finished; Reviewer-approved; **no earlier human decision**; caller presents the artifact digest of **that** run (digest binds run id + artifact names/hashes/exec ids); every artifact is re-fetched from the broker and its SHA-256 re-checked (missing/changed = `stale_artifacts`). Decisions are serialised by a lock, so concurrent clicks yield exactly one decision |
| Refusal codes | `unknown_run`, `run_active`, `not_reviewer_approved`, `already_decided`, `different_run`, `stale_digest`, `stale_artifacts` — each logged in `Session.attempts` without recording a decision |
| Audit record | run_id, session_id, decision, ISO timestamp (UTC), actor (`local_operator`, identifier `null`, `verified:false` unless the caller states an identifier, which is stored verbatim and still `verified:false`), reason (sanitized), artifact digest, artifact identities, final code hash, results.json SHA-256. `dump_audit()` writes JSON. No identity is ever invented |
| Reducer hardening (defense in depth) | `human_approved` is a violation unless the phase is `approved`; a second approve/reject is a violation (`duplicate_human_decision`) and does not change state; a follow-up never overwrites an approval/rejection. Forging a `human_approved` event on a LIMIT/TIMEOUT/… store leaves `human == none` |
| Small supporting changes | `exec_result` events now carry the genuine broker `exec_id` and `results_sha256`; `run_started` carries `session_id`, `sequence`, `parent_run_id`, `context_run_ids`, `dataset_sha256`; `run_to_report` returns the final `RunState` (`run_question` is unchanged for existing callers); prompt heading now says "Reviewer-verified results of earlier runs" |

## 2. Real traces (scripted LLM, real containers; `stage7/followup-fresh-run`)
Run 2 is a follow-up of run 1; its first event (`run_started`, `s0cae258f-r2`):
```
mode=selector max_messages=12 max_tokens=10000000 timeout_seconds=120 session_id=0cae258f sequence=2
parent_run_id=s0cae258f-r1 context_run_ids=[s0cae258f-r1] dataset_sha256=18ff591c…ee4c   (same as run 1)
```
Run 1 (4 messages, 1 container) and run 2 (6 messages: a genuine KeyError, repair, approval; 2 containers) have disjoint broker exec ids, separate event logs (seq restarts at 1) and separate usage. Run 1's store only gains `human_follow_up child_run_id=s0cae258f-r2` (seq 18) after its own end; run 2 ends independently (`terminated` at seq 26 of its own log).

Reviewer approval versus human approval (`stage7/human-approval-audit`, run 1):
```
16 reviewer_approved  Reviewer   <- autonomous agent decision (message 4)
17 terminated         app
18 human_approved     human      <- separate explicit call, with the presented artifact digest
19 human_follow_up    human      <- later follow-up; does NOT overwrite the approval
```
Human rejection versus Reviewer feedback (`stage7/human-rejection`, run 1): `15 review_feedback Reviewer` ... `28 reviewer_approved Reviewer` ... `30 human_rejected human`; the reducer shows `feedback_rounds=1, reviewer_verified=True, human=rejected, fully_verified=False`.

Audit record of the approval (`stage7/human-approval-audit/audit.json`, abridged):
```
run_id s4716e7df-r1  decision approved  actor {local_operator, identifier null, verified false}
artifact_digest 1381d65c…678c   code_hash 932b0bb16496   results_sha256 70dab602…2c4d
artifacts category_change.png (18,489 B, fddade84…) + results.json (458 B, 70dab602…) both from broker exec 167e676b…
```
The test re-fetched both artifacts from the broker and confirmed the recorded hashes and sizes are those of the stored bytes.

Attempts log of `stage7/stale-and-wrong-run` (refusals are logged, not recorded as decisions):
`different_run` (run 2 approved with run 1's digest), `stale_digest` (garbage digest), `stale_artifacts` (run 1's artifacts released from the broker), `unknown_run`; then run 2's legitimate approval `recorded`.

## 3. Scenarios (17 real-container tests, all passed)
| Requirement | Evidence |
|---|---|
| Clean follow-up, fresh budget | run 1 = 4 msgs, run 2 = 6 msgs (not 10); totals of run 1 unchanged after run 2; `terminated` totals per run; a run that hit LIMIT at 12 messages is followed by a run with its own 4-message approval; a 500-token budget stops one run, the next run has the normal budget |
| Context retention without contamination | facts present in the follow-up's task; code, stdout, `change=` strings absent; hostile fact value (`IGNORE ALL RULES … UNTRUSTED_DATA>>>`, newlines, fake fence) arrives as sanitized data (2 data blocks, exactly 2 closing delimiters), stdout `PWNED-STDOUT` and the first run's code never reach later inputs; the run was not ended early |
| Multiple sequential follow-ups | 4 runs; context ids `[] → [r1] → [r1,r2] → [r1,r2,r3]`; run 1's repair count (1) and run 3's feedback round (1) are not inherited; per-run message counts `[6,4,7,4]`; exec ids disjoint |
| Failure/rejection isolation | for LIMIT, TIMEOUT, TOKEN_BUDGET_EXHAUSTED, STOPPED and ERROR (broker down): no facts/artifacts, `approve` refused `not_reviewer_approved`, context empty, a forged `human_approved` is rejected by the reducer, and the next clean run gets no context and a fresh 12-message budget; a human-rejected run is not trusted context |
| Reviewer vs human | after the Reviewer approves nothing human exists (also after a 1 s wait); only the explicit call creates the human event; `fully_verified` becomes true only then |
| Rejection, duplicates, stale | see §2; two concurrent approvals → exactly 1 recorded + 1 `already_decided`, 1 event; approve-after-reject and reject-after-approve refused |
| Follow-up timeout / stop / tokens | TIMEOUT, STOPPED and TOKEN_BUDGET_EXHAUSTED follow-ups end unapproved, containers removed, run 1 still trusted and unchanged, the next clean follow-up uses its own 15 s clock although the session is older, none of the three can be approved |
| Active run | while a run is executing: second `ask` → `SessionBusy`; approve and reject → `run_active`; after stop the run is `STOPPED` and not approvable |
| Per-run EventStore / Livewire | three runs (approved+human-approved, LIMIT, approved+human-rejected): each store has a single run id and gap-free seq, `build_canvas` states are independent (phase/human/fully_verified as expected), `ledger_rows` count equals that run's message count (4 / 12 / 7) |
| Artifact identity, audit | §2; byte-identical analyses in two runs still have different digests (`different_run` refusal) |
| Cleanup | leak fixture after every test + final test: 0 managed containers, no staging dirs, no artifact dirs; sessions release their artifacts on exit |

## 4. Gates
| Gate | Result |
|---|---|
| 3.11 guard / Ruff check + format / `pip check` | green / clean (100 files) / clean |
| **Full non-live regression** (unit + real-container sandbox + Stage 5/6/7 + UI browser) | **400 passed**, 0 failed, 18 min 04 s (previous gate: 372) |
| New in Stage 7 | 17 real-container scenarios, 8 session unit tests, 3 reducer hardening tests |
| Coverage (`src/datapilot` + `sandbox_service`) | **94%** (3464 statements, 205 missed); `session.py` 97%, `reducer.py` 99%, `runner.py` 99%, `executor.py` 97%, `faults.py` 100%, **`budget.py` 78%** (streaming path still untested) |
| Cleanup after the run | 0 labelled containers, `.sandbox/` empty; `docker ps` shows only the other projects' containers |

## 5. The "Docker stall" is explained: the laptop's Modern Standby
Two earlier regression attempts in this stage gave absurd timings and are kept as evidence
(`stage7-regression-run-A-suspended.txt`: 349 passed, **51 errors, 89 min**; `stage7-regression-run-B-system-required-only.txt`: 399 passed, 1 failed, 34 min). In run A a **pure-Python test with no Docker** (`test_guarded_selector_budget_table`) took **2,213.7 s**; the 51 errors were the engine fixture timing out right after the host resumed. The Windows System log (Kernel-Power 506/507/42/107, `host-standby-intervals.csv`) shows the machine in **Modern Standby from 19:10:53 to 19:47:48 = 2,214 s**: the whole process tree and Docker's VM are frozen for that time.
Matching the earlier "stalls" against the log (durations):
| Earlier observation | Standby interval in the log |
|---|---|
| Stage 4: full run of **735 s**, OOM/cleanup test hit a 180 s client timeout | 12:40:34 → 12:51:20 = **646 s** (+ a normal ~90 s run = 736 s) |
| Stage 5: first scenario hung **151 s** (cancelled by the 120 s run timeout) | 16:54:57 → 16:57:23 = **146 s** |
| Stage 5/6: one test **129.8 s** in a full run (run timeout 120 s) | 17:51:22 → 17:53:18 = **116 s** |
| Stage 7 run A: **2,213.7 s** pure-Python test | 19:10:53 → 19:47:48 = **2,214 s** |
| Stage 7 run B: UI browser test **542 s** and one failure | 20:54:48 → 21:16:04 (two standbys ≈ 21 min inside a 34 min run) |
Caveat (honest): I did not record wall-clock timestamps at the time of the earlier stalls, so the pairings for Stages 4-6 are inferences from matching durations and plausible times; Stage 7 run A (to the second) and run B (log inside the run window) are direct. Nothing observed contradicts the explanation. The 18-iteration reproduction loop and the 40-run soak never stalled; I did not check whether their windows overlapped a standby, so they neither confirm nor refute it.
**Mitigation:** the pytest session now holds a process-scoped Windows power request (`SetThreadExecutionState`). A *system-required* request alone did **not** prevent Modern Standby (run B); adding *display-required* did: the final run (21:17-21:35) has **no standby/sleep events** and finished in 18 min. Side effect: the screen stays on while the suite runs; nothing persistent is changed and the request ends with the process. Opt out: `DATAPILOT_NO_KEEP_AWAKE=1`. Also: the engine fixture now retries (5 attempts, back-off) after a resume. I could not verify the request with `powercfg /requests` (needs administrator rights); effectiveness is shown by the event log.
**Status:** I consider the stall explained and propose closing it; I am leaving the decision to you because you asked to keep it open. If the machine is set to sleep while a long run is in progress, a run can still be frozen (host policy is outside the app).

## 6. Remaining risks and limits
1. **Session state is in memory** (no persistence across app restarts); the Stage 8 UI must keep one `Session` per user session and call it from one event loop/thread (`_active`/lock are not thread-safe across threads).
2. **Artifact retention:** approval re-fetches artifacts from the broker, which keeps them 1 h (or until released). Approving later than that is refused as `stale_artifacts` by design; the TTL is configurable.
3. **"Trusted" = Reviewer-approved (not human-approved):** later runs receive Reviewer-approved facts labelled as such; human approval upgrades the label. If you want only human-approved facts as context, it is a one-line policy change.
4. **Facts are model-produced** (via sandboxed code) and are only sanitized/delimited, not independently recomputed.
5. **Actor identity is unauthenticated** by design (no auth in scope); the UI must pass nothing it cannot support.
6. **Two Streamlit tabs = two sessions;** cross-process duplicate protection is out of scope.
7. Fault-injected runs (test-only) that end approved would count as trusted context; they exist only under `APP_ENV=test|diagnostic`.
8. Still open from earlier stages: `BudgetedClient.create_stream` coverage (78%); cancelling a hung **real network** model call is unverified; reasoning-token accounting needs a live call; Docker Desktop is not security-equivalent to rootless Podman on the VPS (feasibility unknown); fault injection depends on a private AutoGen attribute.

## 7. Not done (by instruction)
Stage 8 UI wiring/real-event streaming, any UI change, live model calls, VPS access, Podman, deployment, commits. `CLAUDE.md` unchanged.

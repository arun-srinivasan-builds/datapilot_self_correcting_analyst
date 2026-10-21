# Technical risk register (living)

## R-AG1 — AutoGen is in maintenance mode (decision D10: retain AutoGen)

| | |
|---|---|
| Observation | The AutoGen project README states AutoGen is in maintenance mode (bug/security fixes, no new features) and recommends Microsoft Agent Framework for new work. |
| Why we keep it | The assignment (Use Case 03) mandates AutoGen; the modern AgentChat API (`autogen-agentchat`) is the required surface. D10 approved retention. |
| Pinned versions | `autogen-agentchat==0.7.5`, `autogen-core==0.7.5`, `autogen-ext==0.7.5` (verified installed 2026-10-15 under Python 3.11.9). |
| Impact | No new upstream features; slower fixes; possible incompatibility with future `openai` releases (we pin `openai==3.31.0`). |
| Mitigations | Exact pins; all AutoGen use is confined to `agents/` and `sandbox/executor.py` behind our own interfaces (`RuntimeEvent`, `CodeExecutor`); termination/counting is app-owned, not library-owned; upgrade only with the contract tests (`T-TERM-*`) green. |
| Exit path | If AutoGen becomes unusable, the event model and sandbox contract are framework-neutral; only `agents/participants.py` and `teams.py` would be rewritten. Requires user approval. |

## R-MODEL1 — `gpt-6-luna` parameter constraints (verified 2026-10-15, `docs/evidence/m2/model-check.md`)

| Parameter | Finding | Rule |
|---|---|---|
| `max_tokens` | rejected (HTTP 400) | never send; use `max_completion_tokens` |
| `temperature` | only default (1) accepted | never override |
| `seed` | accepted | may be set (best-effort reproducibility) |
| `model_info` | explicit dict required by AutoGen | `agents/client.py` |
| function calling / structured output | not yet exercised | verify in M3 before relying on them |

AutoGen 0.7.5 accepts `max_completion_tokens` as a create argument (checked offline against the installed `create_kwargs`; mapping is unit-tested without a live call).

## R-PRICE1 — token pricing not configured

Token counts are always captured. Money is shown only when both `PRICE_INPUT_PER_1M` and `PRICE_OUTPUT_PER_1M` are set; otherwise the UI shows "Pricing not configured". No default price exists.

## R-HOST1 — host Modern Standby freezes long test/run sessions (found 2026-10-16)

| | |
|---|---|
| Observation | On the Windows dev laptop, Modern Standby suspends the whole process tree and Docker Desktop's VM. Test timings jump by the standby duration (up to 37 min) and the Docker CLI can time out right after resume. Earlier "unexplained Docker stalls" (Stages 4-7) match the Kernel-Power standby intervals (`docs/evidence/m3/stage7/host-standby-intervals.csv`). |
| Mitigation | pytest holds a process-scoped Windows power request (system + display required; `DATAPILOT_NO_KEEP_AWAKE=1` opts out); the sandbox engine fixture retries after a resume. Production/VPS runs are unaffected (servers do not enter Modern Standby), but any run executing while its host suspends will see timeouts. |
| Residual | If the host is forced to sleep (lid closed, policy), a long run can still be frozen. Wall-clock timeouts count the frozen time. |

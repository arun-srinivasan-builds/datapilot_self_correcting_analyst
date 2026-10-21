# ORCHESTRATOR (development agent)

> Coordinates Claude Code *development* agents to build DataPilot milestone by milestone.
> **Not** an AutoGen runtime participant. The product's Planner/Coder/Executor/Reviewer/User Proxy live in `src/datapilot/agents/`.

## Role
- Read `INITIAL.md` + PRP; own the milestone plan (M1–M7) and gates.
- Decompose a milestone into independent work packages; dispatch dev-agents in parallel where files don't overlap.
- Keep one shared contract: the **event model** (`src/datapilot/events`) and the **results contract** (`results.json`).
- Enforce non-negotiables (below); stop at every gate for user review.
- Maintain `docs/MILESTONES.md` (start/end times, rework cycles).

## Non-negotiables (check before reporting any milestone done)
1. Correction is performed by real agents on real execution errors — no scripted repair.
2. Only Reviewer can approve; 12-message hard cap; counter never resets.
3. Executor failure routes to Coder.
4. Generated code runs only in the sandbox service; no socket/DinD/secrets/network.
5. Livewire shows only real events.
6. No generic Streamlit card layout; responsive; reduced-motion.
7. Python 3.11; `gpt-6-luna` from env; no silent model change.
8. No auto-commit; no VPS/Traefik change without inspection + approval.

## Dev agents

| Agent | File | Owns |
|---|---|---|
| AUTOGEN-AGENT | `agents/autogen-agent.md` | runtime agents, teams, termination, event emission |
| STREAMLIT-UI-AGENT | `agents/streamlit-ui-agent.md` | workspaces, theme, Livewire |
| SANDBOX-AGENT | `agents/sandbox-agent.md` | sandbox service, executor, isolation |
| TEST-AGENT | `agents/test-agent.md` | pytest, evals, viewport tests |
| DEVOPS-AGENT | `agents/devops-agent.md` | Docker, Compose, Traefik, deploy |
| REVIEW-AGENT | `agents/review-agent.md` | security, coverage, UI review |

## Dispatch format

```yaml
TO: autogen-agent
MILESTONE: M3
TASK: Implement Reviewer-sourced termination + 12-message cap
READ: [CLAUDE.md, skills/AUTOGEN.md, PRPs/datapilot-prp.md#termination]
INTERFACES: [events.RuntimeEvent, agents.team.build_team()]
FILES: [src/datapilot/agents/termination.py, tests/agents/test_termination.py]
VALIDATION: [ruff check, pytest tests/agents -q]
CONSTRAINTS: [no mocked behavior in prod path, verify API against installed version]
```

## Parallelism
Dispatch all independent packages in a single response. Typical independent sets: UI shell ∥ ingestion; sandbox service ∥ agent prompts; event bridge ∥ SVG canvas; reports ∥ Insights UI.
Sequential: events contract → team wiring → Livewire binding → e2e.

## Gate protocol
Run gate → capture output → if fail, fix and re-run (count rework) → report with evidence → **stop and wait**.

## Report template
```
MILESTONE M<n> — <name>
Time: <start>–<end> (active) | Rework cycles: k
Built: files…
Evidence: command outputs / logs / screenshots
Deviations & conflicts: …
Open decisions: …
Status: READY FOR REVIEW | BLOCKED (reason)
```

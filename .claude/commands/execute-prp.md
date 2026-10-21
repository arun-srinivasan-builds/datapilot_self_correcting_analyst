# Execute PRP Command

You are the **ORCHESTRATOR** for DataPilot. Execute `PRPs/datapilot-prp.md` **one milestone at a time**, with a review gate between milestones.

## Input
`$ARGUMENTS` = path to PRP, optionally `--milestone M<n>` (default: next incomplete milestone) or `--resume`.

## Read first
- `CLAUDE.md`, `INITIAL.md`, the PRP, `agents/ORCHESTRATOR.md`
- The skills required by the milestone (see table)

## Ground rules
- **One milestone per invocation.** Stop at the gate and wait for user review. Never chain milestones.
- Never commit/push automatically.
- Honour approval boundaries: no VPS/Traefik change, no `gpt-6-luna` substitution, no privileged/DinD or Docker-socket-in-app sandbox, no choice of sandbox isolation level (D3) without approval, no new dependency outside the approved stack without asking.
- Genuine behaviour only: no mocked agent output in production paths or the Livewire.
- Log start/end clock time and rework cycles in `docs/MILESTONES.md` (exclude breaks).
- Parallelism: dispatch independent dev-agents in **one response** (multiple Task calls); sequence dependent ones.

## Milestone playbook

| M | Dev agents | Skills | Parallel set |
|---|---|---|---|
| M2 Foundation + UI shell | STREAMLIT-UI-AGENT, TEST-AGENT, DEVOPS-AGENT (dev env only) | STREAMLIT, BI_UI, TESTING | step 0 `gpt-6-luna` check → (ingestion ∥ test scaffold ∥ mockups) → **mockup approval gate** → shell |
| M3 AutoGen engine | AUTOGEN-AGENT, SANDBOX-AGENT, TEST-AGENT | AUTOGEN, SANDBOX, TESTING | sandbox service ∥ agents/prompts; then team+termination, then e2e |
| M4 Livewire | STREAMLIT-UI-AGENT, AUTOGEN-AGENT, TEST-AGENT | LIVEWIRE, STREAMLIT | event bridge ∥ SVG/CSS canvas; then wire to real stream |
| M5 Insights + stretch | STREAMLIT-UI-AGENT, AUTOGEN-AGENT, TEST-AGENT | BI_UI, TESTING | reports (py/PNG/PDF) ∥ Insights Studio ∥ multi-sheet; then approval/follow-up |
| M6 Quality | TEST-AGENT, REVIEW-AGENT | TESTING, SANDBOX | guardrails/evals ∥ viewport tests; then visual review |
| M7 Deploy + closure | DEVOPS-AGENT, REVIEW-AGENT | DEPLOYMENT | inspect VPS (read-only) → ask approval → deploy → verify |

## Procedure per milestone
1. **Plan** — restate milestone scope + exit criteria from the PRP; list files to create/change.
2. **Dispatch** dev-agents (each prompt: role file, skills, exact files, interfaces, tests, "no mocks in prod paths").
3. **Integrate** — resolve interface mismatches; keep one event model.
4. **Validate gate** (commands below). Failures → fix → re-run; each loop increments the rework count.
5. **Report** — what was built, evidence (command output, logs, screenshots), deviations, open decisions. **Stop.**

## Validation gates

```bash
# G-all (every milestone)
ruff check . && ruff format --check .
pytest -m "not live" -q

# M2: model check, ingestion, mockups, shell
python scripts/check_model.py                # first; stop if model unavailable (no substitution)
pytest tests/ingestion -q
# mockup approval recorded in docs/MILESTONES.md BEFORE any shell code
streamlit run src/datapilot/ui/app.py        # human visual check vs approved mockups

# M3: engine
pytest tests/agents tests/sandbox -q
pytest -m live -k normal_run       # Demo A: no injection
pytest -m live -k fault_injection  # Demo B: labelled test-only injection; real Coder repair
# must show: Reviewer-only APPROVED; approval on 12th valid; 12-msg stop; sandbox no-net/no-secrets; injected faults never presented as natural
# the sandbox isolation level (L2/L3, skills/SANDBOX.md) is stated in the milestone report

# M4: livewire
pytest tests/events tests/ui/test_livewire_mapping.py -q   # event→animation state mapping
# manual: run live scenario; confirm animation tracks real events, no flicker

# M5: outputs
pytest tests/reports -q          # PNG labels/units, analysis.py rerun == identical numbers, PDF == 1 page

# M6: quality
pytest tests/evals tests/ui -q   # Playwright viewports 1920/1366/820/390; screenshots to docs/screens/
# human visual approval required

# M7: deploy
docker compose config && docker compose build
curl -fsS https://<host>/_stcore/health ; WebSocket smoke ; sandbox egress check from inside container
```

## Status display
```
M<n> <name>      [started HH:MM] [rework: k]
 ├─ <dev-agent>  [✅/🔄/❌] <summary>
 └─ Gate         [PASS/FAIL] <failing check>
Awaiting review.
```

## Error handling
Agent fails → capture error → try targeted fix (≤2 cycles) → else mark partial, report, stop. Resume with `--resume`.
Never mask a failing gate; report it with output.

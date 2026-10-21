# DataPilot — Self-Correcting Data Analyst

> Social Eagle AI Academy · Agentic AI track · Assignment 03 (Microsoft AutoGen) — a learning project.

Ask a business question about your sales data in plain English. A team of AutoGen agents plans the analysis, writes Python, runs it in an isolated sandbox, fixes its own errors, and returns a verified answer with charts, `analysis.py`, and a one-page PDF.

## Status

**M1-M6 implemented; M7 (Docker/VPS deploy) not started.** The agents really run: a Planner, Coder, Executor and Reviewer (AutoGen `SelectorGroupChat`, guarded routing) write pandas code, execute it in a per-run Docker sandbox, repair their own errors and are reviewed. Evidence: `docs/evidence/m3/normal-run`, `docs/evidence/m3/fault-injection` (real error -> autonomous repair), `docs/evidence/m5-m6/live`.

## Planned

- Runtime agents: Planner, Coder, Executor, Reviewer, User Proxy (AutoGen AgentChat)
- Autonomous loops: execution error → Coder; Reviewer feedback → Coder; stop on Reviewer `APPROVED` or 12 messages
- Streamlit "Intelligence Studio": Ask & Explore · Agent Livewire · Insights Studio
- Sandboxed code execution; multi-sheet Excel; one-page PDF; `SelectorGroupChat`
- Docker + Traefik deployment on a Hostinger VPS

## Stack

Python 3.11 · AutoGen · `gpt-6-luna` (via env) · Streamlit · pandas · matplotlib · Plotly · openpyxl · ReportLab · pytest · Ruff · Docker · Traefik

## Documentation

| Doc | Purpose |
|---|---|
| [`INITIAL.md`](INITIAL.md) | Product definition, traceability matrix, decisions, conflicts |
| [`CLAUDE.md`](CLAUDE.md) | Rules for Claude Code in this repo |
| [`docs/SocialEagle_UseCase_Definitions.pdf`](docs/SocialEagle_UseCase_Definitions.pdf) | Assignment source (Use Case 03, pp. 9–11) |
| [`docs/MILESTONES.md`](docs/MILESTONES.md) | Milestone time & rework log |
| [`skills/`](skills) | AUTOGEN · STREAMLIT · BI_UI · LIVEWIRE · SANDBOX · TESTING · DEPLOYMENT |
| [`agents/`](agents) | Claude Code *development* agents (not the AutoGen runtime agents) |
| [`.claude/commands/`](.claude/commands) | `/generate-prp`, `/execute-prp`, `/setup-project` |

## Workflow (agentic coding)

```
INITIAL.md → /generate-prp INITIAL.md → PRPs/datapilot-prp.md → /execute-prp (one milestone at a time, review gates)
```

Milestones: M1 Requirements · M2 Foundation & UI shell · M3 AutoGen engine · M4 Livewire · M5 Insights & stretch · M6 Quality · M7 Docker/VPS/closure.


## Run the UI

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pip install -e . --no-deps
copy .env.example .env      # then add OPENAI_API_KEY (never committed)
.venv\Scripts\python -m streamlit run src/datapilot/ui/app.py
```

Add `SANDBOX_TOKEN` (24+ random characters) to `.env` and start Docker Desktop. **Run analysis** starts the loopback sandbox broker on demand and a real run. The labelled *design preview* remains in Livewire only while no live run exists.

Tests: `pytest -m "not live"` (offline + real containers); `pytest -m live tests/live` spends model tokens (accuracy, multi-sheet, prompt injection, reproducibility). `scripts/live_demo.py normal|fault_injection` regenerates the two demonstration evidence folders.

# Setup Project Command (DataPilot)

Read-only **environment readiness check** for DataPilot. It never installs anything and never edits files.

## Check and report

1. **Python 3.11 available** — `py -3.11 --version` (Windows) or `python3.11 --version`. Warn if bare `python` is not 3.11.
2. **Docker** — `docker --version`, `docker compose version`; daemon reachable.
3. **Docs present** — `docs/SocialEagle_UseCase_Definitions.pdf`.
4. **Env vars** — report only whether `OPENAI_API_KEY` / `OPENAI_MODEL` are set (never print values).
5. **Repo state** — `git status --short`, current branch.
6. **Template leftovers** — grep active instruction files for obsolete SaaS terms (FastAPI, React, Alembic, JWT, OAuth, PostgreSQL); list hits and flag any that are not explicit exclusion statements.
7. **Docker-level readiness** — report whether rootless Podman or gVisor is available (informs sandbox decision D3); read-only.

## Output

A table of check → status → remedy. Do not fix automatically; propose commands for the user to run (`! <cmd>`).

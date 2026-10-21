# DEVOPS-AGENT (development agent)

> Containerization, Compose, Traefik, VPS deployment.

## Owns
`Dockerfile` (app), `sandbox_service/Dockerfile`, `docker-compose.yml`, `.env.example`, `.dockerignore`, `docs/DEPLOY.md` (created in M7; does not exist yet), rollback notes, CI (if added).

## Skills
`skills/DEPLOYMENT.md` (mandatory), `skills/SANDBOX.md`.

## Rules
- Python 3.11 base images; pinned requirements; non-root users; healthchecks.
- Two services (`app`, `sandbox`); sandbox on `internal: true` network; only `app` joins the Traefik network.
- Streamlit behind Traefik: WebSocket support, correct `server.baseUrlPath`/headers if sub-pathed, CORS/XSRF settings reviewed.
- **Inspect before change:** read-only inspection of the VPS and existing Traefik (network, entrypoints, cert resolver, existing routers). Present findings and get approval before any apply.
- Secrets via env/secret files, never in images or git.
- Rollback: tagged images, `docker compose` down/up of previous tag, volume handling.

## Output
Files, `docker compose config` output, build logs, verification checklist, rollback steps.

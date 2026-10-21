# Deployment Skill

> Docker + Compose + Traefik on the existing Hostinger VPS. **Inspect before change; approval before apply.**

## Services
- `app` — Streamlit (Python 3.11), no Docker socket, no direct internet need except OpenAI API egress.
- `sandbox` — generated-code runner, internal network only. Pattern below is isolation level L2 (long-running service); it is not a fresh container per execution — see `skills/SANDBOX.md`.

## App Dockerfile (pattern)
```dockerfile
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
RUN useradd -m -u 10001 app && mkdir -p /data && chown -R app /data
USER app
EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1
CMD ["streamlit","run","src/datapilot/ui/app.py","--server.address=0.0.0.0","--server.port=8501","--server.headless=true"]
```

## Compose (pattern; labels are placeholders until the VPS is inspected)
```yaml
services:
  app:
    build: .
    env_file: .env                 # OPENAI_API_KEY etc.; never baked into image
    environment: { SANDBOX_URL: http://sandbox:8080 }
    networks: [traefik_proxy, sandbox_net]
    volumes: [artifacts:/data]
    labels:
      - traefik.enable=true
      - traefik.docker.network=<traefik-network>            # TBD
      - traefik.http.routers.datapilot.rule=Host(`<domain>`)  # TBD
      - traefik.http.routers.datapilot.entrypoints=<websecure> # TBD
      - traefik.http.routers.datapilot.tls.certresolver=<resolver> # TBD
      - traefik.http.services.datapilot.loadbalancer.server.port=8501
  sandbox:
    build: ./sandbox_service
    networks: [sandbox_net]        # internal: true
networks:
  sandbox_net: { internal: true }
  traefik_proxy: { external: true, name: <traefik-network> }   # TBD
volumes: { artifacts: {} }
```

## Streamlit behind Traefik
WebSockets (`/_stcore/stream`) pass through Traefik by default; verify with a live session. If served under a sub-path set `--server.baseUrlPath`. Review `server.enableCORS` / `enableXsrfProtection`; keep XSRF on. Large uploads need `server.maxUploadSize` aligned with `MAX_UPLOAD_MB`.

## VPS procedure (M7)
1. **Read-only inspection**: `docker ps`, `docker network ls`, existing Traefik static/dynamic config, entrypoints, cert resolver, domain/DNS, ports in use, resource headroom. Report; **ask approval**.
2. Build/tag images (`datapilot:<git-sha>`).
3. Deploy with `docker compose up -d`; do not modify other stacks.
4. Verify: health endpoint, HTTPS cert, WebSocket live run, sandbox egress blocked (`docker exec sandbox …`), logs free of secrets.
5. **Rollback**: retain previous tag; `IMAGE_TAG=<prev> docker compose up -d`; keep artifact volume; remove router labels to unpublish.

## Local dev note (Windows)
Docker Desktop available. Use a 3.11 venv explicitly; bare `python` may be 3.14.

## CI (optional)
`ruff check`, `pytest -m "not live"`, `docker compose build`; no secrets in CI logs.

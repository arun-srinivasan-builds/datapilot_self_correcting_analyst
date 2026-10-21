# Deploying DataPilot to the VPS (behind the existing Traefik)

Same pattern as ReviewLens. Two sites, one image, routed by the Traefik already running on the VPS
(`n8n-traefik-1`: entrypoint `websecure`, certificate resolver `mytlschallenge`, network `n8n_default`):

| Hostname | Mode | Access | OpenAI / sandbox |
|----------|------|--------|------------------|
| `datapilot.arunsrinivasan.io` | `demo` | public, no login | never called; container has no key and no sandbox access. Replays **recorded real runs**, labelled as such |
| `datapilot-admin.arunsrinivasan.io` | `live` | password (Traefik basic auth) | real analyses; code runs only in the sandbox broker |

Containers publish no ports, run read-only as a non-root user with all capabilities dropped. Traefik,
n8n and the other apps are not modified.

## Sandbox design (Docker runtime, Unix socket)

```
browser -> Traefik -> datapilot-live (no Docker socket) --unix socket--> broker (host systemd service, user dpsandbox)
                                                                          '-> docker run --rm --network none ... one container per execution
```

- The broker is a host service (standard library only). It listens **only** on
  `/run/datapilot-sandbox/broker.sock` (mode 0660, group `dpsandbox`) plus a bearer token.
- The live container mounts only that socket directory and joins the group (`group_add`).
- **Residual risk (be aware):** the broker's user is in the `docker` group, which is root-equivalent on
  this host, and the Docker daemon is not rootless. A sandbox escape would affect the whole VPS.
  Mitigations: `--network none`, read-only rootfs, all caps dropped, `no-new-privileges`, memory/CPU/PID
  limits, a pinned image, fixed `docker run` arguments (no caller-supplied flags or images), the live
  site behind a password. Rootless Podman would be stronger; it needs `podman` + `uidmap` installed and
  a runtime adapter (not done).
- Capacity: 2 vCPU / ~4.8 GB free at inspection time. The broker runs at most 2 executions at once
  (512 MB, 1 CPU each).

## 0. DNS (once)

`A` records for `datapilot` and `datapilot-admin` pointing at the VPS IP (`187.127.141.104`).

## 1. Get the code

```bash
mkdir -p /srv/datapilot && cd /srv/datapilot
git clone https://github.com/arun-srinivasan-builds/datapilot_self_correcting_analyst.git app
cd app
```

## 2. Host user and directories (review the script first; it only does what its header says)

```bash
less deploy/setup-sandbox-host.sh
sudo bash deploy/setup-sandbox-host.sh      # prints the dpsandbox gid, needed in step 5
```

## 3. Sandbox image (built on the laptop, transferred, so the pinned image id is preserved)

On the laptop:

```powershell
docker save datapilot-sandbox:m3 | gzip > datapilot-sandbox-m3.tar.gz     # use 7-zip/WSL gzip if needed
scp datapilot-sandbox-m3.tar.gz root@187.127.141.104:/tmp/
```

On the VPS:

```bash
docker load < <(gunzip -c /tmp/datapilot-sandbox-m3.tar.gz)
docker image inspect datapilot-sandbox:m3 --format '{{.Id}}'
grep image_id sandbox_service/image/image.lock.json
```

The two ids must match (the broker refuses to start otherwise). If they differ only because this host
stores image ids differently, copy the lock file and set the new id, then set `SANDBOX_IMAGE_LOCK`
(next step):

```bash
sed "s#\"image_id\": \"[^\"]*\"#\"image_id\": \"$(docker image inspect datapilot-sandbox:m3 --format '{{.Id}}')\"#" \
  sandbox_service/image/image.lock.json > /etc/datapilot/image.lock.json
```

## 4. Broker service

```bash
sudo cp deploy/broker.env.example /etc/datapilot/broker.env
sudo chown root:dpsandbox /etc/datapilot/broker.env && sudo chmod 0640 /etc/datapilot/broker.env
sudo nano /etc/datapilot/broker.env     # set SANDBOX_TOKEN (openssl rand -hex 24); SANDBOX_IMAGE_LOCK if step 3 needed it
sudo cp deploy/datapilot-sandbox.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now datapilot-sandbox
systemctl status datapilot-sandbox --no-pager
ls -l /run/datapilot-sandbox/                # srw-rw---- dpsandbox dpsandbox broker.sock
```

## 5. App secrets (on the VPS only, never committed)

```bash
cd /srv/datapilot/app
cp .env.example .env
nano .env     # OPENAI_API_KEY, OPENAI_MODEL=gpt-6-luna, SANDBOX_TOKEN (same as broker.env), MAX_RUN_TOKENS=80000
chmod 600 .env
```

Password protection is Traefik's basic-auth middleware (bcrypt, htpasswd format). Generate the hash
(prompts for the password, so it stays out of shell history):

```bash
docker run --rm -it httpd:2 htpasswd -nBC 12 admin
```

Add to `.env` (hash in single quotes; use only the part after `admin:`), plus the group id from step 2:

```env
ADMIN_USER=admin
ADMIN_PASSWORD_HASH='$2y$12$...'
SANDBOX_GID=<gid printed by setup-sandbox-host.sh>
```

## 6. Launch

```bash
docker compose build
docker compose up -d
docker compose ps
```

`demo` and `live` should be `Up (healthy)`. Traefik requests the certificates on the first visit.

## 7. Verify

```bash
curl -sI https://datapilot.arunsrinivasan.io | head -1                 # 200
curl -sI https://datapilot-admin.arunsrinivasan.io | head -1           # 401
docker compose exec demo env | grep -ciE 'openai|sandbox_token'       # 0
docker compose exec live ls -l /run/datapilot-sandbox/                 # broker.sock visible
docker ps --format '{{.Names}} {{.Status}}'                            # other apps unchanged
```

Then open the admin site, sign in, pick the `sales_sample` dataset, run the suggested question and
watch Agent Livewire. Afterwards `docker ps -a --filter label=datapilot.sandbox=1` must be empty.

## Operations

| Task | Command |
|------|---------|
| Update | `git pull && docker compose build && docker compose up -d` (restart the broker too if `sandbox_service/` changed: `systemctl restart datapilot-sandbox`) |
| Logs | `docker compose logs -f live` / `journalctl -u datapilot-sandbox -f` |
| Rotate OpenAI key | edit `.env`, `docker compose up -d live` |
| Rotate sandbox token | change it in `.env` and `/etc/datapilot/broker.env`, restart both |
| Stop DataPilot only | `docker compose down`; `systemctl stop datapilot-sandbox` (does not affect Traefik or n8n) |

## Rollback / unpublish

```bash
docker compose down                                   # sites disappear; Traefik drops the routers
systemctl disable --now datapilot-sandbox
rm /etc/systemd/system/datapilot-sandbox.service && systemctl daemon-reload
# optional full removal: userdel dpsandbox; rm -rf /srv/datapilot /etc/datapilot; docker rmi datapilot:latest datapilot-sandbox:m3
```

## Safety notes

- Only the live site can call OpenAI or run code; it is behind the password and a 27 MB request cap.
- Uploaded data is processed in memory/temporary storage; generated code has no network.
- Logs contain counts and exception names; AutoGen prompt logging is disabled.
- The demo site replays recordings only: its container has no key and no route to the broker.

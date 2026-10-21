#!/usr/bin/env bash
# DataPilot - one-time host setup for the sandbox broker. Run as root, ONLY after reviewing it.
# It is idempotent and touches nothing that belongs to Traefik, n8n or any other stack.
#
# What it changes (and nothing else):
#   - creates the system user/group `dpsandbox` (no login shell) and adds it to group `docker`
#   - creates /srv/datapilot/sandbox-root and /etc/datapilot
#   - does NOT start anything; the unit is installed by hand afterwards (docs/DEPLOY.md)
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then echo "run as root" >&2; exit 1; fi

id dpsandbox >/dev/null 2>&1 || useradd --system --home-dir /srv/datapilot --shell /usr/sbin/nologin dpsandbox
usermod -aG docker dpsandbox
install -d -o dpsandbox -g dpsandbox -m 0750 /srv/datapilot /srv/datapilot/sandbox-root
install -d -o root -g dpsandbox -m 0750 /etc/datapilot

echo "dpsandbox gid: $(getent group dpsandbox | cut -d: -f3)   <- put this in the app .env as SANDBOX_GID"
echo "done. Next: docs/DEPLOY.md step 4."

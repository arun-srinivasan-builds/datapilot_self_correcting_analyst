#!/usr/bin/env bash
# DataPilot M7 - READ-ONLY VPS inspection (PRP section 6.3 Phase 1 + Traefik/Docker facts).
#
# Changes nothing: no installs, no writes outside stdout, no service restarts, no docker run/exec,
# no config edits. Every command only reads. Secrets are redacted before printing.
#
# Usage (on the VPS):   bash vps_inspect.sh > datapilot-vps-report.txt 2>&1
#   or from your PC:    ssh <user>@<vps> 'bash -s' < scripts/vps_inspect.sh > datapilot-vps-report.txt
# Review the report, then paste it back. Nothing leaves the machine by itself.

set -u
redact() { sed -E 's/((token|secret|password|passwd|apikey|api_key|key|authorization)[A-Za-z_"'\'' -]*[:=] *)[^ ,"'\'']+/\1[REDACTED]/Ig'; }
section() { printf '\n===== %s =====\n' "$1"; }
run() { printf '$ %s\n' "$*"; "$@" 2>&1 | head -n "${LINES_MAX:-60}"; }

section "0. Identity and OS"
run whoami
run id
run uname -a
[ -r /etc/os-release ] && head -n 6 /etc/os-release
run date -u

section "1. Virtualization and kernel"
run systemd-detect-virt
run uname -r

section "2. User namespaces"
run cat /proc/sys/user/max_user_namespaces
run cat /proc/sys/kernel/unprivileged_userns_clone

section "3. cgroups"
run stat -fc %T /sys/fs/cgroup
run cat /sys/fs/cgroup/cgroup.controllers
run sh -c 'cat /sys/fs/cgroup/user.slice/user-*.slice/cgroup.controllers'

section "4. Sub-ID mapping prerequisites"
run sh -c 'grep -c . /etc/subuid /etc/subgid'
run sh -c 'command -v newuidmap newgidmap'

section "5. Podman / container tooling present"
run sh -c 'command -v podman docker crun runc conmon slirp4netns'
run sh -c 'podman --version; docker --version; docker compose version'
run sh -c 'apt-cache policy podman | head -n 6'

section "6. Docker state (read-only listings)"
run docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}'
run docker network ls
run docker volume ls
run sh -c 'docker info --format "root={{.DockerRootDir}} cgroup={{.CgroupVersion}} driver={{.Driver}} rootless={{.SecurityOptions}}"'
run sh -c 'docker ps -q | xargs -r docker inspect --format "{{.Name}} nets={{range \$k,\$v := .NetworkSettings.Networks}}{{\$k}} {{end}}"'

section "7. Listening ports"
run ss -ltnp

section "8. Traefik (labels and static/dynamic config; secrets redacted)"
run sh -c 'docker ps --format "{{.Names}} {{.Image}}" | grep -i traefik'
run sh -c 'for c in $(docker ps --format "{{.Names}}" | grep -i traefik); do echo "--- $c command/args"; docker inspect --format "{{json .Args}}" "$c"; echo "--- $c mounts"; docker inspect --format "{{range .Mounts}}{{.Source}} -> {{.Destination}} ({{.Mode}}){{println}}{{end}}" "$c"; echo "--- $c networks"; docker inspect --format "{{range \$k,\$v := .NetworkSettings.Networks}}{{\$k}} {{end}}" "$c"; done'
for f in /etc/traefik/traefik.yml /etc/traefik/traefik.yaml /opt/traefik/traefik.yml /opt/traefik/traefik.yaml \
         /srv/traefik/traefik.yml /root/traefik/traefik.yml /home/*/traefik/traefik.yml \
         /opt/traefik/docker-compose.yml /root/traefik/docker-compose.yml; do
  if [ -r "$f" ]; then printf '\n--- %s\n' "$f"; redact < "$f" | head -n 120; fi
done
run sh -c 'docker ps --format "{{.Names}}" | xargs -r -I{} sh -c "docker inspect --format \"{{.Name}}: {{range \\\$k,\\\$v := .Config.Labels}}{{if eq (printf \\\"%.8s\\\" \\\$k) \\\"traefik.\\\"}}{{\\\$k}}={{\\\$v}} | {{end}}{{end}}\" {}" | grep "traefik\." | sed -E "s#(basicauth\.users=)[^ |]+#[REDACTED]#g"'

section "9. Resources"
run free -m
run df -h
run nproc
run uptime

section "10. Unix socket path, groups and systemd"
run ls -ld /run /run/user
run getent group docker
run sh -c 'getent passwd | cut -d: -f1,3,6 | head -n 30'
run sh -c 'command -v systemctl && systemctl is-system-running'
run sh -c 'systemctl list-units --type=service --state=running --no-pager | head -n 40'

section "11. Firewall and DNS (read-only)"
run sh -c 'ufw status 2>/dev/null | head -n 20'
run sh -c 'iptables -S 2>/dev/null | head -n 30'
run sh -c 'hostname -f; hostname -I'

printf '\n===== END (nothing was changed) =====\n'

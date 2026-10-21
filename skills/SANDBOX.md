# Secure Sandbox Skill

> AI-generated Python must never run in the Streamlit process, and must not reach secrets, the network, or the host.

## 1. Threat model

Generated code may be buggy or steered by prompt-injected dataset text. Assume it can try to: read environment variables or files, open network connections, exhaust CPU/RAM/PIDs, run forever, write outside its output directory, follow symlinks, read other sessions' data, or attack the sandbox runtime itself.

## 2. Isolation levels — what each one actually gives

| Level | Design | What isolates one run from the next | Verdict |
|---|---|---|---|
| L0 | `exec`/subprocess inside the Streamlit app | nothing | **Forbidden** |
| L1 | App container drives the host Docker socket | fresh container per run, but socket ≈ root on host | **Forbidden** (requirement: no socket in app) |
| L2 | **Long-running sandbox service**; each run is a subprocess with rlimits, per-run directory, minimal env | OS process boundary and file permissions only | **Learning-grade; proposed default (see §3)** |
| L3 | **Fresh ephemeral container per execution**, created by a small broker with narrowly scoped container-create rights (rootless Podman, or a filtered Docker-API proxy), network none, destroyed afterwards | separate PID/mount/network namespaces, fresh filesystem per run | **Stronger; recommended if the VPS allows it** |
| L4 | L3 + user-space kernel/microVM (gVisor `runsc`, Kata, Firecracker) | adds a kernel-attack-surface barrier | Strongest; likely beyond the VPS/learning scope |

**A long-running sandbox service with subprocess isolation (L2) is not equivalent to a fresh isolated container per execution (L3).** Do not describe L2 as "a container per run" anywhere in docs, UI or the completion report.

## 3. L2 limitations (must be documented in the PRP and the final report)

- All runs share one container's PID, mount and network namespaces, kernel and service process. Isolation between runs depends on correct per-run directory permissions, process-group cleanup and rlimits, not on the kernel.
- A process that survives or escapes its process group (double fork, `setsid`, kill-resistant children) can outlive the run and observe later runs. Mitigate by running each job in its own PID namespace if available (`unshare`/`bwrap`), killing the whole process group (or cgroup), and verifying no leftover processes after every run.
- Leftover state (files in `/tmp`, shared memory, `/dev/shm`) can leak between runs unless wiped; each run needs its own tmp dir and `TMPDIR`.
- The service process itself (HTTP handler) sits in the same container as untrusted code; a bug there is reachable from generated code. Run generated code as a different, unprivileged uid than the service, and keep the service's own secrets/config unreadable to that uid.
- No kernel-level defence: a kernel or runc vulnerability breaks every level; only L4 reduces this.
- Resource limits are per process or per container, not per user session; one run can starve another, bounded only by `pids_limit`/`mem_limit`/`cpus` and the timeout.

Acceptable for a learning assignment **only if** the hardening and the must-pass tests in §6 hold. Treat L3 as the upgrade path.

## 4. Stronger alternatives (decision D3 — needs approval before M3)

| Option | How | Cost / risk |
|---|---|---|
| **L3-a Rootless Podman broker** | Broker service uses rootless Podman to `run --rm --network none --read-only --cap-drop ALL --pids-limit … --memory … --cpus …` per execution | Podman on the VPS and compatibility with the existing Docker/Traefik setup must be verified; startup latency per run (~hundreds of ms) |
| **L3-b Docker API via filtered proxy** | A socket proxy exposes only container create/start/wait/remove (no exec, no volumes of arbitrary paths, no privileged) to a *broker* container; the Streamlit app never sees it | The proxy is still a high-value target; allow-list and image pinning must be exact; needs explicit approval |
| **L3-c Pre-warmed pool** | Broker keeps N idle containers and uses each once, then destroys it | Lower latency; more moving parts |
| **L4 gVisor/Kata** | Run L3 containers under `runsc` | Requires host support; likely unavailable on a shared VPS |
| **L2 (default)** | §3 limitations apply | Lowest effort; weakest isolation |

**Decision (D3, approved):** L3 is the target, preferably L3-a (rootless Podman broker). Feasibility is unverified; investigate read-only (`PRPs/datapilot-prp.md §6.3`), install nothing without approval. L3-b/L3-d or L2 are fallbacks that need explicit approval. Keep the `CodeExecutor`/broker interface swappable and state the shipped level honestly in the README and final report.

## 5. Service contract (L2; L3 keeps the same contract)

```
POST /run   {session_id, run_id, code, dataset_ref, timeout_s}
→ {status: ok|error|timeout|killed, exit_code, stdout, stderr, duration_ms,
   artifacts: [{name, size, sha256}], truncated: {stdout, stderr}}
GET  /artifact/{session_id}/{run_id}/{name}   # allow-listed names, size-capped
GET  /health
```
Reachable only from the app over an internal network; request size cap; no secrets in its environment.

### Hardening baseline (Compose)
```yaml
sandbox:
  build: ./sandbox_service
  user: "10001:10001"
  read_only: true
  tmpfs: ["/work:size=256m,mode=0700,uid=10001,gid=10001"]
  cap_drop: [ALL]
  security_opt: ["no-new-privileges:true"]
  pids_limit: 128
  mem_limit: 768m
  cpus: 1.0
  networks: [sandbox_net]        # internal: true -> no egress
```
Runner: `subprocess.Popen(..., start_new_session=True, cwd=run_dir, env=<minimal, no secrets>, preexec_fn=set_rlimits)`; wall-clock timeout; kill the process group; truncate output; `MPLBACKEND=Agg`; wipe the run dir afterwards.

### Controlled access
- Dataset staged as a read-only copy in the run directory; path passed as `DATA_PATH`.
- Outputs only under `OUTPUT_DIR`; serve regular files only (no symlinks), name regex `^[\w.-]+$`, size cap.
- Session and run ids are UUIDs; paths built with `Path.resolve()` plus a prefix check.

## 6. Feasibility and must-pass tests

L3 feasibility checks (rootless Podman, timeout semantics, UID/GID mapping, socket permissions, mount permissions, cleanup, VPS/Traefik compatibility) are specified in `PRPs/datapilot-prp.md §6.3`; they are read-only until installation is approved.

### Must-pass tests (all levels)

no network (DNS and TCP) · environment has no `OPENAI_*` or service secrets · cannot read the service's own files/config · cannot read another run's directory · cannot write outside `OUTPUT_DIR` · symlink/traversal artifact rejected · infinite loop → `timeout` · memory hog → `killed` · fork bomb bounded · **no leftover processes or files after a run** · cleanup removes the run dir · deterministic result for the same script and data.

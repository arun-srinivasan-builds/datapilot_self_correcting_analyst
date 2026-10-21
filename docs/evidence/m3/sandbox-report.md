# M3 Stage 4: Sandbox report

Date: 2026-10-16 · Scope: real isolated execution backend + broker (Stage 4 only).
Raw evidence in this folder: `full-regression.txt` (verbose pytest output incl. every sandbox test),
`sandbox-image.json`, `env-baseline.json`, plus `sandbox_service/image/image.lock.json`.

## 1. Environment (facts)

| Item | Value |
|---|---|
| Host | Windows 11 Pro 10.0.26200, Python 3.11.9 project venv (guard green) |
| Container engine | Docker Desktop (already installed and running; not installed, upgraded or reconfigured), server 29.7.2, Linux containers, cgroup v2, security options `seccomp(builtin)`, `cgroupns`; **not rootless** |
| Base image | `python:3.11-slim` pinned by digest `sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce` (Python 3.11.17, linux/amd64) |
| Execution image | `datapilot-sandbox:m3`, image id `sha256:354c6f52f5ca4be57c36aa01d1bcb8fa0d5580936c0e9a687d886aabe028d638`, 97.6 MB, user 10001:10001, pip/setuptools/wheel removed |
| Packages in image (verified at run time by a test) | pandas 3.0.6 · numpy 2.4.6 · openpyxl 3.1.5 · matplotlib 3.11.2 (identical to the app pins) |
| Broker | standard-library `ThreadingHTTPServer`, loopback only, bearer token; fixed docker CLI argv; refuses to start unless the local image id equals `image.lock.json` |
| Timeout capability probed (decision C2) | `docker run --help` has **no `--timeout`** flag (only `--stop-timeout`). Timeouts are therefore enforced by the broker's own wall-clock watchdog (`docker kill` + `docker rm -f`) |
| Podman | not installed (not authorized). VPS: not inspected |

## 2. What was built

| Component | File |
|---|---|
| Image recipe + lock | `sandbox_service/image/{Dockerfile,requirements.txt,image.lock.json}` |
| Config (loopback-only, token length, safe root) | `sandbox_service/broker/config.py` |
| Runtime adapter + the only `docker create` builder | `sandbox_service/broker/runtime.py` |
| Staging (dataset store, artifact collection, retention, reaper) | `sandbox_service/broker/staging.py` |
| Run lifecycle + watchdog + cancellation | `sandbox_service/broker/manager.py` |
| HTTP API, validation, auth | `sandbox_service/broker/server.py`, `__main__.py` |
| App-side client and backend | `src/datapilot/sandbox/{client,backend}.py` (`BrokerBackend` implements `ExecutionBackend`; cancel -> broker DELETE -> container killed) |
| Token budget enforcement (decision 3) | `src/datapilot/agents/budget.py` |

Container flags (all fixed by the broker, asserted on a *live* container via `docker inspect`):
`--network none --read-only --cap-drop ALL --security-opt no-new-privileges --user 10001:10001
--memory 512m --memory-swap 512m --cpus 1 --pids-limit 128 --ulimit nofile/core/fsize
--tmpfs /tmp (noexec,nosuid,nodev,64m) --shm-size 16m --log-driver none --pull never`;
exactly two bind mounts (`/in` read-only, `/out` writable, both under the broker root); command
`python -I /in/analysis.py`; environment only `DATA_PATH, OUTPUT_DIR, MPLBACKEND, PYTHONHASHSEED,
TZ, HOME, MPLCONFIGDIR` (+ the image's own `PATH/LANG/PYTHON_*`).
Requests can set only: `exec_id`, `code`, `dataset_id`, optional `sheet` and `timeout_s`.

## 3. Test evidence (real containers, real broker)

`pytest -m sandbox`: see `full-regression.txt` for the final counts and per-test lines.

| Requirement | Tests (all green) |
|---|---|
| Network isolation | `test_no_network_no_dns` (TCP to three addresses fails, DNS fails, only `lo` exists) |
| Secret isolation | `test_no_secrets_in_the_container_environment` (canary `OPENAI_API_KEY`, `SANDBOX_TOKEN`, `GITHUB_TOKEN`, `AWS_SECRET_ACCESS_KEY` set in the broker process: none reach the container; env is a strict allow-list); `test_no_docker_socket_and_only_expected_mounts` |
| Host-file / filesystem boundary | `test_filesystem_boundaries` (/in, /, /etc not writable; /tmp noexec; /in lists only analysis.py + data.csv), `test_one_run_cannot_see_another_runs_files`, live `docker inspect` test (mounts, no binds, no devices, no privileged, no host PID/IPC) |
| Identity | `test_runs_as_non_root_without_capabilities_and_no_new_privileges` (uid/gid 10001, CapEff/CapBnd = 0, NoNewPrivs = 1) |
| Timeout | `test_infinite_loop_is_killed_as_timeout` (status `timeout`, exit 124) |
| OOM | `test_memory_hog_is_oom_killed` (status `killed`, exit 137) |
| Process limit | `test_fork_bomb_is_bounded_by_the_pids_limit` (fork fails before 128) |
| Output limits | `test_output_flood_is_truncated`, `test_disk_fill_in_output_dir_is_stopped` (watchdog kills at 64 MB), `test_single_huge_file_cannot_be_written` |
| Safe artifacts | `test_unsafe_outputs_are_rejected_not_collected` (directory, bad name, bad extension, >5 MB rejected), `test_link_like_entries_are_never_copied`, `test_collect_enforces_count_and_total_caps`, download + delete test |
| Cancellation | `test_delete_cancels_a_running_execution_and_removes_the_container`, `test_backend_cancellation_kills_the_container` (cancelling the asyncio task of `BrokerBackend.run` removes the container) |
| Cleanup | success/error/timeout/OOM leave no container, staging dir or artifact; broker restart reaps orphans (running stray container + stale dirs) and a restart *during* a live run; per-test fixture asserts zero leaked containers/staging/artifact dirs after every test |
| Broker rejects unauthorized configuration | 12 forbidden fields (`image, network, privileged, mounts, volumes, command, cmd, env, flags, user, memory, session_id`) -> 400 and nothing started; malformed ids/code/sheet/timeout (17 cases); missing/wrong/Basic token -> 401; wrong Host header -> 421; chunked/length-less -> 411; oversize -> 413; traversal in artifact path -> 400/404; non-loopback bind, weak token, unsafe root -> refuses to start (also as a real process: exit code 2) |
| Dataset integrity | digest mismatch -> 400 and nothing stored; magic-byte checks; idempotent upload; oversize refused before reading; expiry of old datasets/artifacts |
| Deterministic results | `test_identical_code_and_data_give_identical_results` (same stdout; same sha256 for PNG and JSON artifacts across two containers) |
| Concurrency | `test_concurrency_limit_returns_429_not_unbounded_containers` |
| The command builder | `test_create_command_is_fixed...`, `test_hostile_sheet_value_stays_one_argv_element...` |

## 4. Defects found by these tests and fixed during Stage 4
1. A broker restart while a run was collecting artifacts caused HTTP 500 (the reaper deleted the run directory under it). Now handled; no partial output kept.
2. Runs that produced no artifacts, or were cancelled, could leave an artifact directory nobody would delete. Directories are now created only when an artifact is actually copied, and cancelled runs keep nothing.
3. Early error responses (e.g. invalid kind) reset the client connection because the request body was unread. Small bodies are now drained before replying.
4. Uploaded datasets were never expired, and the test fixture could not delete read-only dataset files (49 temporary broker roots had accumulated under `.sandbox/`). Retention added (datasets 6 h, artifacts 1 h, applied at startup and after each run); fixture fixed; leftovers removed.

## 5. Container cleanup evidence
After the final full regression (all sandbox tests executed in sequence, including timeouts, OOM kills, cancellations and simulated restarts):
- `docker ps -a --filter label=datapilot.sandbox=1`: **0** containers; **0** containers named `dpsbx-*`.
- `.sandbox/` (broker root used by tests): **empty** (0 entries).
- Containers of other projects on this machine were never touched: the broker/reaper only act on the `datapilot.sandbox=1` label (11 non-sandbox containers were present at the final check; none were removed by us).
- One transient engine stall was observed once during development (a single full run took 12 minutes and failed a client-side 180 s HTTP timeout in the OOM/cleanup test). It did not reproduce in the more than ten full or partial runs that followed; every docker CLI call is now logged with its duration when slower than 5 s (none seen). Treat it as an open, unexplained risk, not as solved.

## 6. Isolation-level assessment (honest)
**Achieved: per-execution container, created from a fixed server-side recipe, with the broker as the only component holding container-runtime access. This is the PRP's "L3-d" shape (Docker runtime behind the broker) on a Windows development machine.**
**It is not claimed to be equivalent to the proposed rootless-Podman VPS design.** Specifically:
- Docker Desktop runs a root Docker daemon inside a Linux VM. The broker (running as the developer's user) can drive that daemon; a broker bug or token theft therefore reaches a root-equivalent daemon, constrained only by the fixed argv. Rootless Podman would not have a root daemon.
- The container shares the VM's kernel with all other containers on this machine (no gVisor/Kata). A kernel or runc escape would break isolation on any level.
- Bind mounts come from a Windows file system through Docker Desktop's file sharing. UID/GID mapping, file modes (`0777` on `/out`), and symlink behaviour on Linux hosts were **not** exercised and must be re-tested on the VPS before any L3 claim there (PRP F3/F4).
- Rootless Podman feasibility on the VPS is still **UNKNOWN** (no inspection authorized).
Other limitations: no disk quota (the output size is polled every 250 ms and capped per file via `ulimit fsize`, so a fast writer can exceed 64 MB briefly); no I/O or network-bandwidth limits; Docker's default seccomp profile only; the base image contains Debian packages and was not vulnerability-scanned; real host symlink escapes could not be reproduced here (Windows privilege `SeCreateSymbolicLinkPrivilege` missing), so that branch is covered by a stub-driven unit test and by the container-level test, not by an end-to-end real symlink; the broker's own process environment (which may contain app secrets if started from the app's shell) is inherited by the docker CLI process, not by containers; loopback HTTP has no TLS (the bearer token protects against other local processes only if the token file/env is not readable by them); two brokers sharing one machine would reap each other's containers.

## 7. Token budget (decision 3)
- Default `MAX_RUN_TOKENS` is now **30,000** (configurable, > 0), alongside the 12-agent-message cap and the 300 s wall clock; each can end the run independently, and each is reported distinctly (`limit_reached` with `limit` = `messages|tokens|time|stopped`).
- Enforcement is real: every agent *and* the selector client are wrapped in `BudgetedClient`. Usage reported by the model is added after each call (so selector calls count), and before each call the prompt is estimated; a call that would reach the budget is **refused** (no model call is made) and the run ends as `TOKEN_BUDGET_EXHAUSTED`, UNAPPROVED, never human-approvable.
- Limitations: (a) the completion size of a single call is not capped, so a run can overshoot by up to one completion before the next call is refused; (b) the prompt estimate uses the client's local tokenizer approximation; (c) whether `completion_tokens` includes hidden reasoning tokens is unverified (no live call yet): we count exactly what the API reports; (d) 30,000 tokens may be tight for 12 messages of a growing conversation; a run may legitimately end as `TOKEN_BUDGET_EXHAUSTED` before the 12-message cap. This is expected behaviour, to be tuned with real usage numbers in Stage 9.

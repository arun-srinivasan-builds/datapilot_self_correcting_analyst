# SANDBOX-AGENT (development agent)

> Builds the secure execution environment for AI-generated Python.

## Owns
`sandbox_service/` (own Dockerfile, Python 3.11), `src/datapilot/sandbox/` (client + custom `CodeExecutor`), isolation tests.

## Skills
`skills/SANDBOX.md` (mandatory), `skills/DEPLOYMENT.md`, `skills/TESTING.md`.

## Requirements
- Separate container/service; internal-only network (no egress); app has **no Docker socket**; no DinD/privileged without approval.
- Implement behind a swappable `CodeExecutor` so isolation level L2 (long-running service, subprocess per run) can be upgraded to L3 (fresh container per execution). L2 is **not** equivalent to L3; document its limits (`skills/SANDBOX.md` §3).
- Non-root, read-only root FS, `cap_drop: ALL`, `no-new-privileges`, pids/mem/cpu limits, rlimits, wall-clock timeout.
- Dataset mounted read-only; per-session run dir; artifacts only from an allow-listed output dir; reject traversal/symlinks; size caps.
- No `OPENAI_API_KEY` or other secrets in the sandbox environment.
- Returns structured result: status, exit code, stdout, stderr, duration, artifacts (hash + path), truncated flags.
- Cleanup of run dirs; structured logs without secrets.

## Tests (must exist)
network blocked · env has no secrets · cannot read other sessions' dirs · cannot write outside output dir · fork bomb/mem hog/infinite loop terminated · path traversal rejected · deterministic result for same script+data.

## Output
Architecture note stating the isolation level honestly (L2/L3), trade-offs (resolve D3), test results, residual risks.

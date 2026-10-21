"""Latency soak for the sandbox: many real container runs, optional idle gaps, per-phase timings.

Usage: .venv\Scripts\python.exe scripts/sandbox_soak.py --runs 40 --idle-after 10 --idle-seconds 300
Writes JSON (no secrets) to --out. Needs Docker and the pinned image. Only ever touches containers
that carry the datapilot.sandbox label.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import secrets
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sandbox_service.broker.config import BrokerConfig, ImageLock  # noqa: E402
from sandbox_service.broker.manager import RunManager  # noqa: E402
from sandbox_service.broker.runtime import DockerRuntime  # noqa: E402
from sandbox_service.broker.server import make_server  # noqa: E402
from sandbox_service.broker.staging import remove_tree  # noqa: E402

CODES = {
    "ok": "import pandas as pd, os\nprint(len(pd.read_csv(os.environ['DATA_PATH'])))",
    "error": "raise SystemExit(3)",
    "oom": "b=[]\nwhile True: b.append(b'x'*(50*1024*1024))",
    "timeout": "while True: pass",
}
PATTERN = ["ok", "ok", "error", "ok", "oom", "ok", "timeout", "ok"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=24)
    ap.add_argument("--idle-after", type=int, default=0, help="idle once after this many runs")
    ap.add_argument("--idle-seconds", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "docs/evidence/m3/stage5/soak.json"))
    args = ap.parse_args()
    token, root = secrets.token_urlsafe(32), ROOT / ".sandbox" / "soak"
    remove_tree(root)
    cfg = BrokerConfig(token=token, root=root, port=0)
    runtime = DockerRuntime()
    manager = RunManager(cfg, runtime, ImageLock.load(cfg.lock_path))
    manager.startup_reap()
    server = make_server(cfg, manager)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    data = (ROOT / "fixtures/sales_sample.csv").read_bytes()
    sha = hashlib.sha256(data).hexdigest()

    def call(method: str, path: str, body: bytes | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=400)
        conn.request(method, path, body=body, headers={"Authorization": f"Bearer {token}"})
        resp = conn.getresponse()
        return resp.status, resp.read()

    call("PUT", f"/v1/datasets/{sha}?kind=csv", data)
    rows = []
    for i in range(args.runs):
        if args.idle_after and i == args.idle_after:
            time.sleep(args.idle_seconds)
        kind = PATTERN[i % len(PATTERN)]
        exec_id = secrets.token_hex(8)
        body = json.dumps(
            {
                "exec_id": exec_id,
                "code": CODES[kind],
                "dataset_id": sha,
                "timeout_s": 3 if kind == "timeout" else 40,
            }
        )
        t = time.monotonic()
        status, raw = call("POST", "/v1/runs", body.encode())
        wall = int((time.monotonic() - t) * 1000)
        timing = next((x for x in manager.timing_log if x["exec_id"] == exec_id), {})
        rows.append(
            {
                "i": i,
                "kind": kind,
                "http": status,
                "wall_ms": wall,
                **timing,
                "after_idle": bool(args.idle_after and i == args.idle_after),
            }
        )
        call("DELETE", f"/v1/runs/{exec_id}")
    walls = [r["wall_ms"] for r in rows]
    summary = {
        "runs": len(rows),
        "median_ms": int(statistics.median(walls)),
        "max_ms": max(walls),
        "slowest": sorted(rows, key=lambda r: -r["wall_ms"])[:3],
        "per_kind_median_ms": {
            k: int(statistics.median([r["wall_ms"] for r in rows if r["kind"] == k]))
            for k in CODES
            if any(r["kind"] == k for r in rows)
        },
        "slow_over_20s": [r for r in rows if r["wall_ms"] > 20000],
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8"
    )
    manager.shutdown()
    server.shutdown()
    server.server_close()
    remove_tree(root)
    sys.stdout.write(json.dumps(summary, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

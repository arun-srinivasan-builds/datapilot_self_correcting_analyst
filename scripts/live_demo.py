"""M3 Stage 9 live demonstrations against the real model (gpt-6-luna) and the real sandbox.

  python scripts/live_demo.py normal            # Demo A: no injection
  python scripts/live_demo.py fault_injection   # Demo B: test-only labelled fault

Run with the project venv interpreter. Starts the loopback broker as a subprocess, runs ONE
question as a brand-new run, writes the evidence (events.jsonl, summary.json, artifacts) to
docs/evidence/m3/<demo>/ and never prints secrets. Demo B needs APP_ENV=test and
FAULT_INJECTION=bad_column_lookup, which this script sets for itself only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from datapilot.agents.client import build_model_client  # noqa: E402
from datapilot.agents.participants import RoleClients  # noqa: E402
from datapilot.agents.runner import RunConfig  # noqa: E402
from datapilot.config import Settings  # noqa: E402
from datapilot.faults import FaultInjector  # noqa: E402
from datapilot.sandbox.client import BrokerClient  # noqa: E402
from datapilot.session import DatasetRef, Session  # noqa: E402

log = logging.getLogger("live_demo")
QUESTION = "Which category had the biggest revenue drop in September vs August, and which region?"
DATASET = ROOT / "fixtures" / "sales_sample.csv"
TRUTH = json.loads((ROOT / "fixtures" / "sales_sample.truth.json").read_text(encoding="utf-8"))


def start_broker(settings: Settings) -> subprocess.Popen[bytes]:
    env = {
        **os.environ,
        "SANDBOX_TOKEN": settings.sandbox_token.get_secret_value(),
        "SANDBOX_PORT": "8765",
        "SANDBOX_ROOT": str(ROOT / ".sandbox"),
    }
    return subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "sandbox_service.broker"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


async def main(demo: str) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    for noisy in ("autogen_core", "httpx", "autogen_agentchat"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    overrides = (
        {"app_env": "test", "fault_injection": "bad_column_lookup"} if demo != "normal" else {}
    )
    settings = Settings(**overrides)  # type: ignore[arg-type]
    if not settings.has_api_key or not settings.sandbox_token.get_secret_value():
        log.error("OPENAI_API_KEY and SANDBOX_TOKEN must be configured")
        return 2
    out = (
        ROOT
        / "docs"
        / "evidence"
        / "m3"
        / ("normal-run" if demo == "normal" else "fault-injection")
    )
    out.mkdir(parents=True, exist_ok=True)
    broker_proc = start_broker(settings)
    try:
        broker = BrokerClient("http://127.0.0.1:8765", settings.sandbox_token.get_secret_value())
        for _ in range(40):
            if await broker.healthy():
                break
            time.sleep(0.5)
        else:
            log.error("broker did not become healthy")
            return 3
        fault = (
            FaultInjector.authorized(settings, "bad_column_lookup") if demo != "normal" else None
        )
        config = RunConfig.from_settings(settings, "selector")
        config = RunConfig(
            config.mode, config.max_messages, config.max_tokens, config.timeout_seconds,
            completion_ceiling=config.completion_ceiling, fault=fault,
        )  # fmt: skip
        model = build_model_client(settings)
        session = Session(DatasetRef.from_path(DATASET), broker)
        record = await session.ask(
            QUESTION, clients=RoleClients.shared(model), selector_client=model, config=config
        )
        store = session.store(record.run_id)
        store.dump_jsonl(out / "events.jsonl")
        for art in record.artifacts:
            (out / art.name).write_bytes(
                await broker.artifact(record.artifacts[0].exec_id, art.name)
            )
        summary = {
            "demo": demo,
            "run_id": record.run_id,
            "outcome": record.outcome.value,
            "reviewer_approved": record.reviewer_approved,
            "messages": record.messages,
            "tokens": {"input": record.input_tokens, "output": record.output_tokens},
            "usage_by_source": record.usage_by_source,
            "exec_count": len(record.exec_ids),
            "code_hashes": list(record.code_hashes),
            "facts": list(record.facts),
            "artifacts": [a.to_dict() for a in record.artifacts],
            "ground_truth": TRUTH,
            "fault_records": [
                {"fault": r.fault, "diff": r.diff, "original_hash": r.original_hash,
                 "mutated_hash": r.mutated_hash} for r in (fault.records if fault else [])
            ],
        }  # fmt: skip
        (out / "summary.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
        log.info(
            "outcome=%s messages=%s execs=%s",
            record.outcome.value,
            record.messages,
            len(record.exec_ids),
        )
        await session.release_all()
        return 0
    finally:
        broker_proc.terminate()


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("normal", "fault_injection"):
        sys.exit("usage: live_demo.py normal|fault_injection")
    sys.exit(asyncio.run(main(sys.argv[1])))

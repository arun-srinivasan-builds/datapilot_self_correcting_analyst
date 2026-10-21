"""Live suite: REAL gpt-6-luna + REAL sandbox. Run explicitly with `pytest -m live tests/live`.

Costs model tokens. `MAX_RUN_TOKENS` defaults to 80000 here (override with LIVE_MAX_RUN_TOKENS)
because a repair plus a review round does not fit in the 30000 production default.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from datapilot.agents.client import build_model_client
from datapilot.agents.participants import RoleClients
from datapilot.agents.runner import RunConfig
from datapilot.config import Settings
from datapilot.events import EventType, RuntimeEvent
from datapilot.sandbox.client import BrokerClient
from datapilot.session import DatasetRef, RunRecord, Session

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "evidence" / "m5-m6" / "live"
PORT = 8766


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/live" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.live)


@pytest.fixture(scope="session")
def live_settings() -> Settings:
    os.environ["MAX_RUN_TOKENS"] = os.environ.get("LIVE_MAX_RUN_TOKENS", "80000")
    settings = Settings()
    if not settings.has_api_key or not settings.sandbox_token.get_secret_value():
        pytest.fail("live tests need OPENAI_API_KEY and SANDBOX_TOKEN (never skipped silently)")
    return settings


@pytest.fixture(scope="session")
def broker_url(live_settings: Settings) -> Iterator[str]:
    token = live_settings.sandbox_token.get_secret_value()
    env = {
        **os.environ,
        "SANDBOX_TOKEN": token,
        "SANDBOX_PORT": str(PORT),
        "SANDBOX_ROOT": str(ROOT / ".sandbox-live"),
    }
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "sandbox_service.broker"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{PORT}"
    client = BrokerClient(url, token)
    deadline = time.time() + 40
    healthy = False
    while time.time() < deadline and not healthy:
        healthy = asyncio.run(client.healthy())
        if not healthy:
            time.sleep(0.5)
    if not healthy:
        proc.terminate()
        pytest.fail("broker did not become healthy (is Docker Desktop running?)")
    yield url
    proc.terminate()


Ask = Callable[..., Coroutine[Any, Any, tuple[RunRecord, tuple[RuntimeEvent, ...], Session]]]


@pytest_asyncio.fixture
async def ask(live_settings: Settings, broker_url: str) -> AsyncIterator[Ask]:
    broker = BrokerClient(broker_url, live_settings.sandbox_token.get_secret_value())
    sessions: list[Session] = []

    async def _ask(
        path: Path, question: str, *, sheet: str | None = None, name: str = "run"
    ) -> tuple[RunRecord, tuple[RuntimeEvent, ...], Session]:
        session = Session(DatasetRef.from_path(path, sheet), broker)
        sessions.append(session)
        model = build_model_client(live_settings)
        record = await session.ask(
            question,
            clients=RoleClients.shared(model),
            selector_client=model,
            config=RunConfig.from_settings(live_settings, "selector"),
        )
        events = session.store(record.run_id).snapshot()
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        session.store(record.run_id).dump_jsonl(EVIDENCE / f"{name}.events.jsonl")
        (EVIDENCE / f"{name}.summary.json").write_text(
            json.dumps(
                {
                    "outcome": record.outcome.value,
                    "messages": record.messages,
                    "tokens": [record.input_tokens, record.output_tokens],
                    "facts": list(record.facts),
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        return record, events, session

    yield _ask
    for session in sessions:
        await session.release_all()


def fact_text(record: RunRecord) -> str:
    return " | ".join(f"{f['label']}: {f['value']}" for f in record.facts)


def executed_ok(events: tuple[RuntimeEvent, ...]) -> bool:
    return any(e.type is EventType.EXEC_RESULT and e.payload.get("status") == "ok" for e in events)

"""Bridge between Streamlit (synchronous, reruns) and the real AutoGen run (async, long-lived).

One daemon thread owns an asyncio loop. `LiveSession.ask` schedules `Session.ask` on it and returns
at once; the UI polls `events()` (the run's real `EventStore`) from `st.fragment(run_every=...)`.
No event is produced here: this module only starts, stops and observes real runs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections.abc import Coroutine
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlparse

import streamlit as st

from datapilot.agents.client import build_model_client
from datapilot.agents.participants import RoleClients
from datapilot.agents.runner import RunConfig, RunControl
from datapilot.agents.teams import Mode
from datapilot.config import PROJECT_ROOT, Settings, get_settings
from datapilot.events import EventStore, EventType, RuntimeEvent
from datapilot.reports.repro import Reproducibility, verify_reproducible
from datapilot.sandbox.client import BrokerClient
from datapilot.sandbox.contracts import SandboxUnavailableError
from datapilot.session import Actor, ApprovalRefused, DatasetRef, RunRecord, Session

log = logging.getLogger(__name__)
T = TypeVar("T")
LOOPBACK = ("127.0.0.1", "localhost", "::1")
_ARTIFACT_LIMIT = 8_000_000


class LiveUnavailableError(RuntimeError):
    """Live runs cannot start (missing key/token, broker or container engine down)."""


@dataclass
class RunView:
    """What the UI needs about one run after it ends (bytes are cached; the sandbox is not polled)."""

    record: RunRecord
    events: tuple[RuntimeEvent, ...]
    artifacts: dict[str, bytes] = field(default_factory=dict)
    code: str = ""


class Runtime:
    """Process-wide: the event-loop thread and the loopback sandbox broker."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="datapilot-live", daemon=True)
        self._thread.start()
        self._broker_proc: subprocess.Popen[bytes] | None = None
        self._broker_lock = threading.Lock()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro: Coroutine[Any, Any, T]) -> Future[T]:
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def broker(self, settings: Settings) -> BrokerClient:
        """A client for a healthy broker; starts the loopback broker subprocess if needed."""
        token = settings.sandbox_token.get_secret_value()
        url = urlparse(settings.sandbox_url)
        client = BrokerClient(settings.sandbox_url, token)
        with self._broker_lock:
            if self.submit(client.healthy()).result(10):
                return client
            if url.hostname not in LOOPBACK:
                # Containerised / remote deployment: the broker is a separate service. The app
                # never starts it (it holds no container runtime access by design).
                raise LiveUnavailableError(
                    "The sandbox broker is not reachable. Check the broker service and SANDBOX_URL."
                )
            if self._broker_proc is None or self._broker_proc.poll() is not None:
                env = {
                    **os.environ,
                    "SANDBOX_TOKEN": token,
                    "SANDBOX_PORT": str(url.port or 8765),
                    "SANDBOX_ROOT": str(PROJECT_ROOT / ".sandbox"),
                }
                self._broker_proc = subprocess.Popen(  # noqa: S603
                    [sys.executable, "-m", "sandbox_service.broker"],
                    cwd=PROJECT_ROOT,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            for _ in range(60):
                if self.submit(client.healthy()).result(10):
                    return client
                if self._broker_proc.poll() is not None:
                    break
                time.sleep(0.5)
        raise LiveUnavailableError(
            "The sandbox broker is not available. Start Docker Desktop and retry."
        )


@st.cache_resource
def runtime() -> Runtime:
    return Runtime()


def readiness(settings: Settings | None = None) -> str | None:
    """Why a live run cannot start right now, or None when it can."""
    if os.environ.get("DATAPILOT_MODE", "live").lower() == "demo":
        return "Demo site: runs are recorded real runs. Use the private live site to analyse."
    s = settings or get_settings()
    if not s.has_api_key:
        return "OPENAI_API_KEY is not configured in .env."
    if not s.sandbox_token.get_secret_value():
        return "SANDBOX_TOKEN is not configured in .env."
    return None


class LiveSession:
    """One Streamlit session: a dataset, its runs, and the active run (if any)."""

    def __init__(self, rt: Runtime, settings: Settings) -> None:
        self.rt, self.settings = rt, settings
        self.session: Session | None = None
        self._dataset_key: tuple[str, str | None, float] | None = None
        self.control: RunControl | None = None
        self.future: Future[RunRecord] | None = None
        self.current_run_id: str | None = None
        self.error: str | None = None
        self.views: dict[str, RunView] = {}
        self.order: list[str] = []

    # --------------------------------------------------------------------- state ---------
    @property
    def running(self) -> bool:
        return self.future is not None and not self.future.done()

    def events(self, run_id: str | None = None) -> tuple[RuntimeEvent, ...]:
        run_id = run_id or self.current_run_id
        if run_id is None:
            return ()
        view = self.views.get(run_id)
        if view is not None:
            return view.events
        try:
            return self.session.store(run_id).snapshot() if self.session else ()
        except KeyError:
            return ()  # the run has been scheduled but its store does not exist yet

    def latest_view(self) -> RunView | None:
        self._collect()
        return self.views.get(self.order[-1]) if self.order else None

    # --------------------------------------------------------------------- actions -------
    def ask(
        self,
        question: str,
        *,
        path: Path,
        sheet: str | None,
        mode: Mode,
        parent_run_id: str | None = None,
    ) -> None:
        if self.running:
            raise LiveUnavailableError("A run is already in progress.")
        if (why := readiness(self.settings)) is not None:
            raise LiveUnavailableError(why)
        self._collect()
        self.error = None
        key = (str(path), sheet, path.stat().st_mtime)
        if self.session is None or key != self._dataset_key:
            broker = self.rt.broker(self.settings)
            self.session = Session(DatasetRef.from_path(path, sheet), broker)
            self._dataset_key = key
            self.views.clear()
            self.order.clear()
        session = self.session
        self.current_run_id = f"s{session.session_id}-r{len(session.runs) + 1}"
        self.control = RunControl()
        model = build_model_client(self.settings)
        config = RunConfig.from_settings(self.settings, mode)  # never carries a fault injector
        self.future = self.rt.submit(
            session.ask(
                question,
                clients=RoleClients.shared(model),
                selector_client=model,
                config=config,
                control=self.control,
                parent_run_id=parent_run_id,
            )
        )

    def stop(self) -> None:
        if self.control is not None and self.running:
            self.control.stop()

    def _collect(self) -> None:
        """Move a finished run into `views` (events, cached artifacts, code) exactly once."""
        fut = self.future
        if fut is None or not fut.done() or self.session is None:
            return
        self.future = None
        try:
            record = fut.result()
        except Exception as exc:
            log.exception("live run failed")
            self.error = f"{type(exc).__name__}: {exc}"[:400]
            return
        events = self.session.store(record.run_id).snapshot()
        arts: dict[str, bytes] = {}
        if record.reviewer_approved:
            for ref in record.artifacts:
                if ref.size > _ARTIFACT_LIMIT:
                    continue
                try:
                    arts[ref.name] = self.rt.submit(
                        self.session._broker.artifact(ref.exec_id, ref.name)  # noqa: SLF001
                    ).result(30)
                except (SandboxUnavailableError, TimeoutError):
                    log.warning("artifact %s could not be fetched", ref.name)
        code = next(
            (
                str(e.payload.get("code", ""))
                for e in reversed(events)
                if e.type is EventType.CODE_GENERATED
                and e.payload.get("code_hash") == record.code_hash
            ),
            "",
        )
        self.views[record.run_id] = RunView(record, events, arts, code)
        self.order.append(record.run_id)

    def verify(self, run_id: str, script: str) -> Reproducibility | None:
        """Re-run the exported script in a fresh container and compare answer facts."""
        view = self.views.get(run_id)
        if view is None or self.session is None or "results.json" not in view.artifacts:
            return None
        original = view.artifacts["results.json"].decode("utf-8")
        return self.rt.submit(
            verify_reproducible(script, original, self.session.make_backend(), run_id=run_id)
        ).result(180)

    def decide(self, run_id: str, approve: bool, reason: str = "") -> str | None:
        """Human decision. Returns an error message when refused, else None."""
        self._collect()
        if self.session is None:
            return "No session."
        view = self.views.get(run_id)
        if view is None:
            return "The run has not finished."
        try:
            if approve:
                self.rt.submit(
                    self.session.approve(run_id, artifact_digest_seen=view.record.digest)
                ).result(60)
            else:
                self.session.reject(run_id, reason=reason, actor=Actor())
        except ApprovalRefused as exc:
            return str(exc)
        # refresh the cached record (human decision attached)
        self.views[run_id] = RunView(
            self.session.run(run_id),
            self.session.store(run_id).snapshot(),
            view.artifacts,
            view.code,
        )
        return None


def get_live() -> LiveSession:
    ss = st.session_state
    if os.environ.get("DATAPILOT_MODE", "live").lower() == "demo":
        from datapilot.ui.demo import DemoSession

        return DemoSession()  # type: ignore[return-value]
    if "live" not in ss:
        ss["live"] = LiveSession(runtime(), get_settings())
    return ss["live"]


def results_payload(view: RunView) -> dict[str, Any]:
    raw = view.artifacts.get("results.json")
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


__all__ = [
    "EventStore",
    "LiveSession",
    "LiveUnavailableError",
    "RunView",
    "get_live",
    "readiness",
    "results_payload",
    "runtime",
]

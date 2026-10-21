"""Public demo mode: replays RECORDED real runs (captured from live gpt-6-luna + sandbox executions).

Nothing here calls a model or the sandbox, and nothing is simulated: every event, number and chart
was produced by a real run and saved by `scripts/live_demo.py` (see demo_data/*/summary.json). The UI
labels this clearly as a recorded run. `DemoSession` mirrors the read-only part of `LiveSession`, so
the Livewire and Insights workspaces render the same way for live and recorded runs.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from datapilot.agents.termination import RunOutcome
from datapilot.events import EventType, RuntimeEvent
from datapilot.session import ArtifactRef, RunRecord
from datapilot.ui.live import LiveUnavailableError, RunView

DEMO_DIR = Path(
    os.environ.get("DATAPILOT_DEMO_DIR", Path(__file__).resolve().parents[3] / "demo_data")
)
QUESTION = "Which category had the biggest revenue drop in September vs August, and which region?"
LABELS = {
    "normal-run": "Normal run — approved first time",
    "fault-injection": "Test fault — real error, autonomous repair",
}
DEMO_NOTICE = (
    "RECORDED REAL RUN — captured from a live gpt-6-luna run executed in the isolated sandbox. "
    "This public site cannot start analyses; the private live site can."
)


def is_demo() -> bool:
    return os.environ.get("DATAPILOT_MODE", "live").lower() == "demo"


def _event(raw: dict[str, Any]) -> RuntimeEvent:
    return RuntimeEvent(
        seq=int(raw["seq"]),
        run_id=str(raw["run_id"]),
        ts=datetime.fromisoformat(raw["ts"]),
        type=EventType(raw["type"]),
        source=str(raw["source"]),
        payload=raw.get("payload", {}),
    )


def _load_one(folder: Path, sequence: int) -> RunView | None:
    summary_path, events_path = folder / "summary.json", folder / "events.jsonl"
    if not (summary_path.is_file() and events_path.is_file()):
        return None
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    events = tuple(
        _event(json.loads(line))
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    artifacts = {
        p.name: p.read_bytes()
        for p in folder.iterdir()
        if p.suffix in (".png", ".json") and p.name != "summary.json"
    }
    ok_exec = [
        e for e in events if e.type is EventType.EXEC_RESULT and e.payload.get("status") == "ok"
    ]
    code_hash = str(ok_exec[-1].payload.get("code_hash", "")) if ok_exec else ""
    code = next(
        (
            str(e.payload.get("code", ""))
            for e in reversed(events)
            if e.type is EventType.CODE_GENERATED and e.payload.get("code_hash") == code_hash
        ),
        "",
    )
    approved = summary.get("outcome") == RunOutcome.REVIEWER_APPROVED.value
    refs = tuple(
        ArtifactRef(a["name"], int(a["size"]), a["sha256"], str(a.get("exec_id", "")))
        for a in summary.get("artifacts", [])
    )
    record = RunRecord(
        run_id=str(summary.get("run_id", folder.name)),
        sequence=sequence,
        question=QUESTION,
        outcome=RunOutcome(summary["outcome"]),
        reviewer_approved=approved,
        started_at=events[0].ts.isoformat(timespec="seconds") if events else "",
        finished_at=events[-1].ts.isoformat(timespec="seconds") if events else "",
        parent_run_id=None,
        context_run_ids=(),
        messages=int(summary.get("messages", 0)),
        input_tokens=int(summary.get("tokens", {}).get("input", 0)),
        output_tokens=int(summary.get("tokens", {}).get("output", 0)),
        usage_by_source=summary.get("usage_by_source", {}),
        exec_ids=(),
        code_hashes=tuple(summary.get("code_hashes", ())),
        facts=tuple(summary.get("facts", ())),
        artifacts=refs if approved else (),
        code_hash=code_hash if approved else "",
    )
    return RunView(record, events, artifacts if approved else {}, code if approved else "")


@st.cache_resource(show_spinner=False)
def recorded_runs() -> dict[str, RunView]:
    views: dict[str, RunView] = {}
    for i, name in enumerate(LABELS, start=1):
        view = _load_one(DEMO_DIR / name, i)
        if view is not None:
            views[name] = view
    return views


class DemoSession:
    """Read-only stand-in for `LiveSession`: never starts a run, never touches a model or sandbox."""

    is_demo = True
    running = False
    error: str | None = None
    session = None

    def __init__(self) -> None:
        runs = recorded_runs()
        self.views = {v.record.run_id: v for v in runs.values()}
        self.keys = {k: v.record.run_id for k, v in runs.items()}
        self.order = list(self.views)
        self.control = None

    @property
    def selected_key(self) -> str:
        key = st.session_state.get("demo_run")
        return key if key in self.keys else next(iter(self.keys), "")

    @property
    def current_run_id(self) -> str | None:
        return self.keys.get(self.selected_key)

    def events(self, run_id: str | None = None) -> tuple[RuntimeEvent, ...]:
        view = self.views.get(run_id or self.current_run_id or "")
        return view.events if view else ()

    def latest_view(self) -> RunView | None:
        return self.views.get(self.current_run_id or "")

    def ask(self, *_: Any, **__: Any) -> None:
        raise LiveUnavailableError("Demo site: analyses are recorded. Use the private live site.")

    def stop(self) -> None:  # pragma: no cover - never running
        return None

    def decide(self, *_: Any, **__: Any) -> str:
        return "Human decisions are disabled on the demo site."

    def verify(self, *_: Any, **__: Any) -> None:
        return None


def picker() -> None:
    """Segmented control that chooses which recorded run to show."""
    st.segmented_control(
        "Recorded run",
        list(LABELS),
        format_func=LABELS.get,
        key="demo_run",
        default=next(iter(LABELS)),
    )

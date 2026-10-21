"""Public demo mode: replays RECORDED real runs (captured from live gpt-6-luna + sandbox executions).

Nothing here calls a model or the sandbox, and nothing is simulated: every event, number and chart
was produced by a real run and saved by `scripts/live_demo.py` (see demo_data/*/summary.json). The public page
(demo_page.py) labels this clearly as a recorded run.
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
from datapilot.ui.live import RunView

DEMO_DIR = Path(
    os.environ.get("DATAPILOT_DEMO_DIR", Path(__file__).resolve().parents[3] / "demo_data")
)
QUESTION = "Which category had the biggest revenue drop in September vs August, and which region?"
LABELS = {
    "normal-run": "Normal run — approved first time",
    "fault-injection": "Test fault — real error, autonomous repair",
}


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

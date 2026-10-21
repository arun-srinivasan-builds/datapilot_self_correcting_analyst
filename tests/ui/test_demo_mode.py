"""Public demo mode: recorded REAL runs replayed; nothing can start a run, call a model or decide."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from datapilot.events import EventType
from datapilot.ui import demo

ROOT = Path(__file__).resolve().parents[2]
APP = str(ROOT / "src" / "datapilot" / "ui" / "app.py")


@pytest.fixture(autouse=True)
def _demo_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATAPILOT_MODE", "demo")
    monkeypatch.setenv("DATAPILOT_DEMO_DIR", str(ROOT / "demo_data"))
    monkeypatch.setenv("DATAPILOT_CONTAINER", "1")
    demo.recorded_runs.clear()


def run_app(**state: object) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def body(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


def test_recorded_runs_load_from_real_evidence() -> None:
    runs = demo.recorded_runs()
    assert set(runs) == set(demo.LABELS)
    normal, fault = runs["normal-run"], runs["fault-injection"]
    assert normal.record.reviewer_approved and fault.record.reviewer_approved
    assert normal.artifacts.get("results.json") and normal.code
    # the fault run really contains a failed execution followed by a repaired one
    results = [e for e in fault.events if e.type is EventType.EXEC_RESULT]
    assert [e.payload.get("status") for e in results] == ["error", "ok"]
    assert any(e.type is EventType.TEST_FAULT_INJECTED for e in fault.events)
    assert not any(e.type is EventType.TEST_FAULT_INJECTED for e in normal.events)


def test_livewire_shows_the_recorded_run_with_a_clear_label() -> None:
    text = body(run_app(ws="livewire"))
    assert "RECORDED REAL RUN" in text and "RECORDED RUN" in text
    assert "Reviewer approved" in text


def test_livewire_replay_slider_steps_through_real_events() -> None:
    at = run_app(ws="livewire")
    slider = at.slider[0]
    assert slider.value == slider.max
    slider.set_value(3).run()
    assert not at.exception
    text = body(at)
    assert "APPROVED" not in text.split("MESSAGE LEDGER")[-1]  # not approved yet at event 3


def test_insights_shows_exports_but_no_human_decision_or_follow_up() -> None:
    at = run_app(ws="insights")
    text = body(at)
    assert "RECORDED REAL RUN" in text and "Answer facts" in text
    assert not [b for b in at.button if "Approve report" in str(b.label)]
    assert not [t for t in at.text_input if "Follow-up" in str(t.label)]


def test_fault_run_is_labelled_as_a_test_fault_not_a_natural_error() -> None:
    text = body(run_app(ws="livewire", demo_run="fault-injection"))
    assert "TEST FAULT INJECTED" in text


def test_explore_cannot_start_a_run_on_the_demo_site() -> None:
    at = run_app(ws="explore", q="anything")
    assert at.button(key="run").disabled
    assert "Demo site" in " ".join(c.value for c in at.caption)


def test_demo_module_imports_no_model_sandbox_or_fault_code() -> None:
    tree = ast.parse((ROOT / "src" / "datapilot" / "ui" / "demo.py").read_text(encoding="utf-8"))
    banned = ("autogen", "openai", "datapilot.sandbox", "datapilot.faults", "httpx")
    names = [
        n
        for node in ast.walk(tree)
        for n in (
            [a.name for a in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
            if isinstance(node, ast.ImportFrom)
            else []
        )
    ]
    assert [n for n in names if n.startswith(banned)] == []

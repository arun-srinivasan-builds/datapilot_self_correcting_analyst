"""Public demo page: plain-language story over RECORDED real runs (frames, charts, animation, page)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from datapilot.events import EventType
from datapilot.ui import demo
from datapilot.ui.demo_charts import build_figure, compact, has_data, takeaway
from datapilot.ui.demo_flow import workflow_html
from datapilot.ui.demo_frames import Frame, build_frames, trust_checks

ROOT = Path(__file__).resolve().parents[2]
APP = str(ROOT / "src" / "datapilot" / "ui" / "app.py")
UI = ROOT / "src" / "datapilot" / "ui"


@pytest.fixture(autouse=True)
def _demo_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATAPILOT_MODE", "demo")
    monkeypatch.setenv("DATAPILOT_DEMO_DIR", str(ROOT / "demo_data"))
    monkeypatch.setenv("DATAPILOT_CONTAINER", "1")
    demo.recorded_runs.clear()


def run_app(**state: object) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def body(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


# ----------------------------------------------------------------------------- recorded data ---
def test_recorded_runs_are_real_approved_runs_with_chart_data() -> None:
    runs = demo.recorded_runs()
    assert set(runs) == {"normal-run", "fault-injection"}
    for view in runs.values():
        assert view.record.reviewer_approved and view.code
        results = json.loads(view.artifacts["results.json"])
        assert results["charts"] and all(has_data(c) for c in results["charts"])
        assert (
            not any(e.type is EventType.TEST_FAULT_INJECTED for e in view.events)
            or view is runs["fault-injection"]
        )


# --------------------------------------------------------------------------------- frames ------
def kinds(key: str) -> list[str]:
    return [f.kind for f in build_frames(demo.recorded_runs()[key].events)]


def test_normal_run_frames_tell_the_story_in_order() -> None:
    assert kinds("normal-run") == ["question", "plan", "code", "run_ok", "approve", "done"]


def test_fault_run_frames_show_crash_then_repair() -> None:
    assert kinds("fault-injection") == [
        "question", "plan", "code", "run_fail", "code", "run_ok", "approve", "done",
    ]  # fmt: skip
    frames = build_frames(demo.recorded_runs()["fault-injection"].events)
    first_code, second_code = [f for f in frames if f.kind == "code"]
    assert "TEST ONLY" in first_code.badge and second_code.badge == ""
    assert second_code.loop_back and "fixes" in second_code.title
    crash = next(f for f in frames if f.kind == "run_fail")
    assert "KeyError" in crash.detail and crash.tone == "bad"


@pytest.mark.parametrize("key", ["normal-run", "fault-injection"])
def test_frame_counters_and_times_follow_the_real_events(key: str) -> None:
    view = demo.recorded_runs()[key]
    frames = build_frames(view.events)
    assert [f.count for f in frames] == sorted(f.count for f in frames)
    assert frames[-1].count == view.record.messages
    assert [f.seconds for f in frames] == sorted(f.seconds for f in frames)


def test_trust_checks_are_derived_from_events() -> None:
    normal = trust_checks(demo.recorded_runs()["normal-run"].events)
    fault = trust_checks(demo.recorded_runs()["fault-injection"].events)
    assert any(c.ok is None and "No crash" in c.title for c in normal)
    assert any("caught and fixed" in c.title and "KeyError" in c.body for c in fault)
    assert all(any("Reviewer" in c.title for c in checks) for checks in (normal, fault))


# --------------------------------------------------------------------------------- charts ------
def test_compact_number_formatting() -> None:
    assert (
        compact(-3_980_399.85) == "−3.98M"
        and compact(1_234) == "1,234"
        and compact(25_000) == "25.0K"
    )


@pytest.mark.parametrize("key", ["normal-run", "fault-injection"])
def test_every_recorded_chart_builds_a_native_figure(key: str) -> None:
    results = json.loads(demo.recorded_runs()[key].artifacts["results.json"])
    for chart in results["charts"]:
        fig = build_figure(chart)
        assert len(fig.data) == len(chart["data"]["series"])
        assert fig.layout.paper_bgcolor == "rgba(0,0,0,0)"


def test_takeaway_names_the_largest_fall_from_the_plotted_numbers() -> None:
    chart = {
        "data": {"categories": ["A", "B", "C"], "series": [{"name": "s", "values": [5, -9, 1]}]}
    }
    assert takeaway(chart) == "Biggest fall: B (−9)."


def test_hostile_series_names_cannot_inject_markup_into_hover() -> None:
    chart = {
        "title": "t",
        "data": {"categories": ["a", "b"], "series": [
            {"name": "<img src=x onerror=alert(1)>", "values": [1, 2]}, {"name": "ok", "values": [2, 3]}]},
    }  # fmt: skip
    fig = build_figure(chart)
    assert "<img" not in fig.data[0].hovertemplate


# --------------------------------------------------------------------------- animation html -----
def test_workflow_html_escapes_recorded_text() -> None:
    frame = Frame(
        0, 0.0, "You", "question", "neutral", "</script><img src=x onerror=alert(1)>", "<b>&</b>"
    )
    html = workflow_html([frame])
    assert "</script><img" not in html and "<b>&</b>" not in html
    assert "\\u003c/script" in html
    assert "textContent" in html  # recorded values are only ever set as text


def test_workflow_html_is_self_contained_and_respects_reduced_motion() -> None:
    html = workflow_html(build_frames(demo.recorded_runs()["normal-run"].events))
    assert "prefers-reduced-motion" in html and "http://" not in html.replace(
        "http://www.w3.org", ""
    )
    assert "<script src" not in html


# -------------------------------------------------------------------------------- the page ------
def test_page_tells_the_story_in_four_numbered_sections() -> None:
    at = run_app()
    text = body(at)
    for needle in (
        "Ask a business question",
        "The question",
        "Watch the team work",
        "The answer",
        "Why you can trust it",
        "Recorded real run",
    ):
        assert needle in text
    assert len(at.get("iframe")) == 1  # the animated workflow
    assert "Approve report" not in text and "Run analysis" not in text


def test_switching_to_run_b_shows_the_repair_evidence() -> None:
    text = body(run_app(demo_run="fault-injection"))
    assert "caught and fixed" in text and "planted on purpose" in text


def test_page_has_downloads_for_code_pdf_and_chart() -> None:
    at = run_app()
    labels = " ".join(str(getattr(b, "label", "")) for b in at.get("download_button"))
    assert "analysis.py" in labels and "PDF" in labels and "PNG" in labels


def test_admin_mode_is_unchanged_and_has_the_workspaces(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATAPILOT_MODE", raising=False)
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert not at.exception
    text = body(at)
    assert "Ask a business question" not in text and "Ask & Explore" in text


# ---------------------------------------------------------------------------- import hygiene ---
@pytest.mark.parametrize("module", ["demo_page", "demo_frames", "demo_flow", "demo_charts"])
def test_demo_modules_import_no_model_sandbox_or_fault_code(module: str) -> None:
    tree = ast.parse((UI / f"{module}.py").read_text(encoding="utf-8"))
    banned = (
        "autogen",
        "openai",
        "datapilot.sandbox",
        "datapilot.faults",
        "httpx",
        "datapilot.agents",
    )
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

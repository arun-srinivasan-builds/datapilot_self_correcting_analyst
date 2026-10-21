"""Headless Streamlit smoke tests (no browser): the real script runs, widgets behave, state is honest."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[2] / "src" / "datapilot" / "ui" / "app.py")


def fresh() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    return at


def texts(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


def test_starts_without_exception_on_ask_and_explore():
    at = fresh()
    assert not at.exception
    assert at.session_state["ws"] == "explore"
    assert "Start with your data" in texts(at)
    run = at.button(key="run")
    assert run.disabled  # live agents are M3; nothing is faked


def test_sample_dataset_loads_through_real_ingestion():
    at = fresh()
    at.selectbox(key="sample").set_value("sales_sample.csv").run()
    assert not at.exception
    loaded = at.session_state["loaded"]
    assert loaded is not None and len(loaded.dataset.frame) == 12_480
    assert any(b.key and str(b.key).startswith("sugg-") for b in at.button)
    assert "12,480" in texts(at)


def test_multi_sheet_workbook_offers_sheet_picker():
    at = fresh()
    at.selectbox(key="sample").set_value("multisheet.xlsx").run()
    assert not at.exception
    assert [o for o in at.selectbox(key="sheet").options] == ["Orders", "Returns", "Targets"]
    at.selectbox(key="sheet").set_value("Returns").run()
    assert len(at.session_state["loaded"].dataset.frame) == 150


def test_navigation_between_workspaces_keeps_dataset():
    at = fresh()
    at.selectbox(key="sample").set_value("sales_sample.csv").run()
    at.button(key="nav-livewire").click().run()
    assert at.session_state["ws"] == "livewire" and not at.exception
    assert "Waiting for the first real event" in texts(at)  # genuine idle, no preview
    at.button(key="nav-insights").click().run()
    assert at.session_state["ws"] == "insights" and not at.exception
    assert "No analysis yet" in texts(at)
    at.button(key="nav-explore").click().run()
    assert at.session_state["loaded"] is not None


def test_livewire_design_preview_is_labelled_and_event_driven():
    at = fresh()
    at.session_state["ws"] = "livewire"
    at.session_state["preview_key"] = "repair"
    at.run()
    assert not at.exception
    body = texts(at)
    assert "DESIGN PREVIEW" in body and "Not a live run" in body
    assert "Repairing" in body
    assert "3/12" in body


def test_insights_preview_and_human_stage_rules():
    at = fresh()
    at.session_state["ws"] = "insights"
    at.session_state["preview_key"] = "approved"
    at.run()
    assert not at.exception
    assert not at.button(key="approve").disabled
    assert all(at.button(key=f"dl-{i}").disabled for i in range(3))  # no fabricated exports
    at.button(key="approve").click().run()
    assert at.session_state["human"] == "approved"
    assert "Human approved" in texts(at)


@pytest.mark.parametrize("key", ["limit-reached", "running"])
def test_unapproved_runs_cannot_be_human_approved(key):
    at = fresh()
    at.session_state["ws"] = "insights"
    at.session_state["preview_key"] = key
    at.run()
    assert not at.exception
    if key == "limit-reached":
        assert at.button(key="approve").disabled
        assert "UNAPPROVED" in texts(at)
    else:
        assert "No analysis yet" in texts(at)


@pytest.mark.parametrize("tab", ["Plan", "Code", "Output / stderr", "Reviewer", "Tokens"])
def test_inspector_tabs_render_real_event_evidence(tab):
    at = fresh()
    at.session_state["ws"] = "livewire"
    at.session_state["preview_key"] = "reviewer-feedback"
    at.run()
    at.get("button_group")  # segmented controls exist
    at.session_state["inspector"] = tab
    at.run()
    assert not at.exception
    body = texts(at)
    expect = {
        "Plan": "group by month",
        "Code": "groupby",
        "Output / stderr": "2 charts",
        "Reviewer": "axis label",
        "Tokens": "no figures are shown",
    }[tab]
    assert expect in body


def test_invalid_file_shows_ingestion_error_not_a_crash(tmp_path):
    bad = tmp_path / "dup.csv"
    bad.write_text("a,b,A\n1,2,3\n")
    at = fresh()
    at.session_state["source"] = {"kind": "upload", "name": "dup.csv", "path": str(bad)}
    at.run()
    assert not at.exception
    assert any("Duplicate column names" in e.value for e in at.error)
    assert at.session_state["loaded"] is None


def test_missing_file_is_reported_not_raised(tmp_path):
    at = fresh()
    at.session_state["source"] = {
        "kind": "upload",
        "name": "gone.csv",
        "path": str(tmp_path / "gone.csv"),
    }
    at.run()
    assert not at.exception
    assert any("no longer available" in e.value or "does not exist" in e.value for e in at.error)

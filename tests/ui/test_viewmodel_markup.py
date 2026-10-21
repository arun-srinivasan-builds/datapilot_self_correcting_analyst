from __future__ import annotations

import json
from pathlib import Path

import pytest

from datapilot.events import EventType, reduce_events
from datapilot.ingestion import load_dataset, profile_frame
from datapilot.ui import markup as h
from datapilot.ui.charts import columns, hbar, money_m, variants
from datapilot.ui.preview import SCENARIO_ORDER, events_for, fixture_analysis
from datapilot.ui.viewmodel import build_canvas, feed_items, ledger_rows
from datapilot.ui.workspaces.explore import suggestions

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("key", SCENARIO_ORDER)
def test_every_scenario_is_invariant_clean(key):
    state = reduce_events(events_for(key))
    assert state.violations == ()
    assert state.message_count <= 12
    assert len(ledger_rows(events_for(key))) == state.message_count


EXPECTED = {
    "running": (1, "running"),
    "exec-error": (3, "running"),
    "repair": (3, "running"),
    "reviewer-feedback": (6, "running"),
    "approved": (9, "approved"),
    "limit-reached": (12, "limit_reached"),
    "fault-injection": (3, "running"),
}


@pytest.mark.parametrize(("key", "expected"), EXPECTED.items())
def test_scenario_counts_and_phase(key, expected):
    s = reduce_events(events_for(key))
    assert (s.message_count, s.phase) == expected


def test_no_events_is_a_genuine_idle_canvas():
    c = build_canvas(events_for(None))
    assert c.state.phase == "idle" and c.state.message_count == 0
    assert {v.label for k, v in c.nodes.items() if k != "Human"} == {"IDLE"}
    assert c.nodes["Human"].label == "NOT STARTED"
    assert c.edges == {} and not c.fault


def test_repair_state_shows_real_error_and_animates_repair_edge_only():
    c = build_canvas(events_for("repair"))
    assert c.nodes["Executor"].status == "error" and c.nodes["Executor"].label == "ERROR · EXIT 1"
    assert c.nodes["Coder"].label == "REPAIRING · ATTEMPT 1"
    assert c.edges["repair"] == "repair"
    assert c.edges.get("feedback") != "feedback"
    assert c.nodes["Reviewer"].label == "WAITING"


def test_feedback_state_has_distinct_loop():
    c = build_canvas(events_for("reviewer-feedback"))
    assert c.edges["feedback"] == "feedback" and c.edges["repair"] == "used"
    assert c.nodes["Reviewer"].status == "feedback"
    assert c.nodes["Executor"].status == "ok"


def test_human_stage_is_separate_from_reviewer_approval():
    c = build_canvas(events_for("approved"))
    assert c.nodes["Reviewer"].status == "approved"
    assert c.nodes["Human"].status == "pending" and c.nodes["Human"].label == "PENDING DECISION"
    done = build_canvas(events_for("approved", "approved"))
    assert done.state.fully_verified and done.nodes["Human"].status == "approved"
    # a human cannot make an unapproved run verified
    lim = build_canvas(events_for("limit-reached", "approved"))
    assert not lim.state.fully_verified
    assert lim.nodes["Reviewer"].label == "NEVER APPROVED"


def test_fault_injection_is_persistently_flagged():
    c = build_canvas(events_for("fault-injection"))
    assert c.fault
    assert any(i.who.startswith("test_harness") for i in feed_items(events_for("fault-injection")))
    svg = h.flow_svg(c)
    assert svg.count("TEST FAULT INJECTED") == 2  # horizontal + vertical lanes


def test_events_carry_no_token_usage_in_preview():
    assert not any(e.type is EventType.USAGE for k in SCENARIO_ORDER for e in events_for(k))


def test_markup_escapes_untrusted_dataset_text():
    evil = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'
    assert "<script>" not in h.chip(evil)
    assert "<script>" not in h.table(["c"], [[h.escape(evil)]])  # callers escape cells
    assert "<script>" not in h.highlight(f"x = '{evil}'")
    assert "<script>" not in h.err_block(evil)
    rows = [h.LedgerRow(1, "Coder", "code_generated", evil, "")] if hasattr(h, "LedgerRow") else []
    from datapilot.ui.viewmodel import LedgerRow

    assert "<script>" not in h.ledger_html(
        [LedgerRow(1, "Coder", "code_generated", evil, ""), *rows[:0]]
    )


def test_suggestions_are_schema_driven(fx):
    sample = load_dataset(fx["sample"])
    alt = load_dataset(fx["alt"])
    from datapilot.ui.state import Loaded

    s1 = suggestions(Loaded(sample, profile_frame(sample.frame), {"order_date": ("", "")}))
    s2 = suggestions(Loaded(alt, profile_frame(alt.frame), {"txn_date": ("", "")}))
    assert s1 and s2 and s1 != s2
    assert any("net_amount" in t or "quantity" in t for t in s2)
    assert not any("region" in t for t in s2)  # nothing hardcoded to the sample schema


def test_fixture_analysis_matches_independent_ground_truth(fx):
    a = fixture_analysis(fx["sample"])
    truth = json.loads(fx["sample_truth"].read_text())
    assert a is not None
    assert a.top_category == truth["biggest_drop_category"]
    assert a.top_region == truth["top_region_for_that_drop"]
    assert a.category_change[0][1] == pytest.approx(truth["biggest_drop_amount"], abs=0.01)
    assert a.rows == truth["rows"]


def test_charts_labels_and_variants():
    items = [("Electronics", -3.98e6), ("Home", -0.96e6), ("Beauty", 0.61e6)]
    svg = hbar(items, "t", "x", "Electronics", w=1000)
    assert "−₹3.98M" in svg and "+₹0.61M" in svg and 'class="neg"' in svg
    assert money_m(-3.98e6, True) == "−₹3.98M"
    cols = columns([("2026-08", 63.1e6), ("2026-09", 58.4e6)], "t", "y", "2026-09", w=700)
    assert 'class="neg"' in cols and "58.4" in cols
    v = variants(hbar, items, "t", "x", "Electronics", wide=1000, mid=700)
    assert all(f'class="{k}"' in v for k in ("cw", "cm", "ct", "cn"))


def test_theme_is_light_and_has_required_tokens():
    css = (ROOT / "src/datapilot/ui/static/theme.css").read_text(encoding="utf-8")
    for token in ("--canvas: #f7f6f2", "--surface: #ffffff", "--ink: #233247", "--accent: #077a86"):
        assert token in css
    assert "#0b1426" not in css.lower()  # the superseded dark navy is gone
    assert "prefers-reduced-motion" in css


def test_multiline_blocks_use_entity_newlines_so_streamlit_keeps_line_breaks():
    nl = chr(10)
    code = nl.join(["a = 1", "b = 2", "c = a + b"])
    err = nl.join(["Traceback", "  File x", "KeyError: 'y'"])
    for block in (h.code_block(code), h.err_block(err), h.text_block(nl.join(["1. a", "2. b"]))):
        inner = block.split(">", 1)[1].rsplit("</div>", 1)[0]
        assert nl not in inner and "&#10;" in inner

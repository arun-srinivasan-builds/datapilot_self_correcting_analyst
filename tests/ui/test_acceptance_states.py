"""M2 acceptance: all eight Livewire states, human/Reviewer separation and non-live labelling."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from datapilot.events import AGENTS, EventStore, EventType, reduce_events
from datapilot.ui.preview import SCENARIO_ORDER, SCENARIOS, events_for
from datapilot.ui.viewmodel import build_canvas, ledger_rows

ROOT = Path(__file__).resolve().parents[2]
APP = str(ROOT / "src" / "datapilot" / "ui" / "app.py")
MID = "·"

# state key (None = genuine idle) -> expectations derived from the event semantics, not from the output
EIGHT = {
    None: dict(count=0, run="Idle", nodes=("IDLE", "IDLE", "IDLE", "IDLE", "NOT STARTED")),
    "running": dict(
        count=1, run="Running", nodes=("DONE", "WRITING CODE", "WAITING", "WAITING", "AFTER REVIEW")
    ),
    "exec-error": dict(
        count=3,
        run="Running",
        nodes=("DONE", "DONE", f"ERROR {MID} EXIT 1", "WAITING", "AFTER REVIEW"),
    ),
    "repair": dict(
        count=3,
        run=f"Repairing {MID} attempt 1",
        nodes=(
            "DONE",
            f"REPAIRING {MID} ATTEMPT 1",
            f"ERROR {MID} EXIT 1",
            "WAITING",
            "AFTER REVIEW",
        ),
    ),
    "reviewer-feedback": dict(
        count=6,
        run="Running",
        nodes=("DONE", "REVISING", f"OK {MID} EXIT 0", f"FEEDBACK {MID} 2 ISSUES", "AFTER REVIEW"),
    ),
    "approved": dict(
        count=9,
        run=f"Reviewer approved {MID} 9/12",
        nodes=("DONE", "DONE", f"OK {MID} EXIT 0", f"APPROVED {MID} MSG 9", "PENDING DECISION"),
    ),
    "limit-reached": dict(
        count=12,
        run=f"Unapproved {MID} limit 12/12",
        nodes=("DONE", "DONE", f"OK {MID} EXIT 0", "NEVER APPROVED", "RUN UNAPPROVED"),
    ),
    "fault-injection": dict(
        count=3,
        run=f"Repairing {MID} attempt 1",
        nodes=(
            "DONE",
            f"REPAIRING {MID} ATTEMPT 1",
            f"ERROR {MID} EXIT 1",
            "WAITING",
            "AFTER REVIEW",
        ),
    ),
}
NODE_ORDER = ("Planner", "Coder", "Executor", "Reviewer", "Human")


def run_app(**state) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    assert not at.exception
    return at


def body(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


def test_the_eight_states_are_exactly_idle_plus_seven_scenarios():
    assert set(EIGHT) == {None, *SCENARIOS}
    assert len(EIGHT) == 8 and list(SCENARIO_ORDER) == [k for k in EIGHT if k]


@pytest.mark.parametrize("key", list(EIGHT), ids=lambda k: k or "idle")
def test_state_labels_and_counter_from_events(key):
    exp = EIGHT[key]
    c = build_canvas(events_for(key))
    assert tuple(c.nodes[n].label for n in NODE_ORDER) == exp["nodes"]
    assert c.state.message_count == exp["count"]
    assert c.state.violations == ()


@pytest.mark.parametrize("key", list(EIGHT), ids=lambda k: k or "idle")
def test_state_renders_in_the_running_app(key):
    exp = EIGHT[key]
    at = run_app(ws="livewire", preview_key=key)
    text = body(at)
    assert exp["run"] in text
    assert f">{exp['count']}/12<" in text  # the toolbar counter
    for label in exp["nodes"]:
        assert label in text  # node status text in the lanes SVG
    assert ("DESIGN PREVIEW" in text) is (key is not None)
    assert ("Not a live run" in text) is (key is not None)


def test_reviewer_approval_never_implies_human_approval():
    events = events_for("approved")
    s = reduce_events(events)
    assert s.phase == "approved" and s.human == "none" and not s.fully_verified
    assert not any(e.type in (EventType.HUMAN_APPROVED, EventType.HUMAN_REJECTED) for e in events)
    at = run_app(ws="insights", preview_key="approved")
    assert "Human approval pending" in body(at) and "Human approved" not in body(at)
    assert not at.button(key="approve").disabled  # available, but nothing was auto-approved
    assert at.session_state["human"] is None
    at.button(key="approve").click().run()
    assert at.session_state["human"] == "approved"
    final = reduce_events(events_for("approved", "approved"))
    assert final.fully_verified


def test_limit_reached_run_cannot_be_approved_by_the_human():
    for human in ("approved",):
        s = reduce_events(events_for("limit-reached", human))
        assert s.phase == "limit_reached" and s.human == "none" and not s.fully_verified
    at = run_app(
        ws="insights", preview_key="limit-reached", human="approved"
    )  # even a forged state
    text = body(at)
    assert at.button(key="approve").disabled
    assert "Human approved" not in text and "UNAPPROVED" in text
    # the lanes never show the human stage as approved either
    assert (
        build_canvas(events_for("limit-reached", "approved")).nodes["Human"].label
        == "RUN UNAPPROVED"
    )


def test_test_fault_injected_is_visible_throughout_the_fault_scenario():
    events = events_for("fault-injection")
    first = next(i for i, e in enumerate(events) if e.type is EventType.TEST_FAULT_INJECTED)
    for n in range(first + 1, len(events) + 1):  # every step after the injection
        c = build_canvas(events[:n])
        assert c.fault, f"badge lost at event {n}"
        assert c.state.fault_injected
    assert not any(
        build_canvas(events_for(k)).fault for k in SCENARIO_ORDER if k != "fault-injection"
    )
    for ws in ("explore", "livewire", "insights"):  # persistent chip on every workspace
        text = body(run_app(ws=ws, preview_key="fault-injection"))
        assert "TEST FAULT INJECTED" in text, ws
    lanes = body(run_app(ws="livewire", preview_key="fault-injection"))
    assert lanes.count("TEST FAULT INJECTED") >= 4  # chip + feed + badge in both lane layouts


def test_fault_injection_never_styled_as_a_natural_error():
    events = events_for("fault-injection")
    inj = next(e for e in events if e.type is EventType.TEST_FAULT_INJECTED)
    assert "test_harness" in inj.source
    text = body(run_app(ws="livewire", preview_key="fault-injection"))
    assert "not a natural error" in text and "TEST ONLY" in text


@pytest.mark.parametrize("key", list(SCENARIO_ORDER))
def test_counter_counts_only_agent_messages(key):
    events = events_for(key)
    agent_msgs = [e for e in events if e.type is EventType.AGENT_MESSAGE and e.source in AGENTS]
    others = [e for e in events if e not in agent_msgs]
    s = reduce_events(events)
    assert s.message_count == len(agent_msgs) == len(ledger_rows(events))
    assert others, "scenario should include non-message events"
    # extra non-message events (task message, guardrail, usage, human) never move the counter
    store = EventStore("x")
    for e in events:
        store.append(e.type, e.source, dict(e.payload))
    store.append(EventType.GUARDRAIL, "guardrail", {"rule": "r"})
    store.append(EventType.USAGE, "Coder", {"input_tokens": 10, "output_tokens": 5})
    after = reduce_events(store.snapshot())
    assert after.message_count == s.message_count
    run_started = [e for e in events if e.type is EventType.RUN_STARTED]
    assert run_started and all(
        e.type is not EventType.AGENT_MESSAGE for e in run_started
    )  # task msg


def test_no_preview_state_is_represented_as_autogen_execution():
    for key in SCENARIO_ORDER:
        assert all(e.payload.get("preview") is True for e in events_for(key)), key
    # the scripted preview module itself never imports AutoGen (live runs go through ui.live only)
    code = (
        "import sys; sys.path.insert(0, r'%s');"
        "import datapilot.ui.preview;"
        "bad=[m for m in sys.modules if m.startswith(('autogen', 'openai'))];"
        "print(','.join(bad)); sys.exit(1 if bad else 0)" % (ROOT / "src")
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)  # noqa: S603
    assert r.returncode == 0, r.stdout + r.stderr
    at = run_app(ws="explore")
    assert at.button(key="run").disabled  # no dataset / question yet: nothing can start
    for key in SCENARIO_ORDER:
        text = body(run_app(ws="livewire", preview_key=key))
        assert "Not a live run" in text and "not AI output" in text
    ins = body(run_app(ws="insights", preview_key="approved"))
    assert "not output of a live agent run" in ins.lower() or "not AI output" in ins
    assert "tokens" not in ins.lower() or "no figures" in ins.lower()

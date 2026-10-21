from __future__ import annotations

import dataclasses
import json
import threading

import pytest

from datapilot.events import EventStore, reduce_events
from datapilot.events import EventType as T


def run(*steps: tuple[T, str, dict]) -> tuple:
    store = EventStore("r1")
    for t, src, payload in steps:
        store.append(t, src, payload)
    return store.snapshot()


def msg(src: str) -> tuple[T, str, dict]:
    return (T.AGENT_MESSAGE, src, {"content": "x"})


START = (T.RUN_STARTED, "app", {"question": "q"})
EXEC_OK = (T.EXEC_RESULT, "Executor", {"status": "ok"})
EXEC_ERR = (T.EXEC_RESULT, "Executor", {"status": "error", "stderr": "KeyError"})
APPROVED = (T.REVIEWER_APPROVED, "Reviewer", {})


def test_store_assigns_gap_free_seq_and_is_thread_safe():
    store = EventStore("r")

    def work():
        for _ in range(200):
            store.append(T.GUARDRAIL, "g", {})

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [e.seq for e in store.snapshot()] == list(range(1, 1601))
    assert len(store.since(1590)) == 10


def test_events_are_immutable_and_json_serialisable():
    ev = EventStore("r").append(T.EXEC_RESULT, "Executor", {"status": "ok", "artifacts": ["a.png"]})
    with pytest.raises(dataclasses.FrozenInstanceError):
        ev.seq = 9  # type: ignore[misc]
    with pytest.raises(TypeError):
        ev.payload["status"] = "error"  # type: ignore[index]
    assert isinstance(ev.payload["artifacts"], tuple)
    assert json.loads(json.dumps(ev.to_dict()))["payload"]["artifacts"] == ["a.png"]


def test_source_is_required():
    with pytest.raises(ValueError):
        EventStore("r").append(T.GUARDRAIL, "  ", {})


def test_clean_run():
    s = reduce_events(
        run(
            START, msg("Planner"), msg("Coder"), EXEC_OK, msg("Executor"), msg("Reviewer"), APPROVED
        )
    )
    assert s.phase == "approved" and s.message_count == 4 and s.reviewer_verified
    assert s.violations == () and s.human == "none" and not s.fully_verified
    assert s.nodes["Reviewer"] == "approved"


def test_error_repair_feedback_then_approval():
    s = reduce_events(
        run(
            START,
            msg("Planner"),
            msg("Coder"),
            (T.EXEC_STARTED, "Executor", {}),
            EXEC_ERR,
            msg("Executor"),
            (T.REPAIR_ROUTED, "app", {"attempt": 1}),
            msg("Coder"),
            EXEC_OK,
            msg("Executor"),
            (T.REVIEW_FEEDBACK, "Reviewer", {}),
            msg("Reviewer"),
            msg("Coder"),
            EXEC_OK,
            msg("Executor"),
            msg("Reviewer"),
            APPROVED,
        )
    )
    assert s.phase == "approved"
    assert (s.repair_attempts, s.feedback_rounds, s.message_count) == (1, 1, 9)
    assert s.last_exec_ok is True


def test_limit_reached_is_unapproved():
    events = [START] + [msg(a) for a in ("Planner", "Coder", "Executor", "Reviewer") * 3]
    s = reduce_events(run(*events, (T.LIMIT_REACHED, "app", {"count": 12})))
    assert s.phase == "limit_reached" and s.message_count == 12
    assert not s.reviewer_verified and s.violations == ()


def test_counter_overflow_is_flagged_not_hidden():
    s = reduce_events(run(START, *[msg("Coder") for _ in range(13)]))
    assert s.message_count == 13 and any(v.startswith("cap_exceeded") for v in s.violations)


def test_approval_from_wrong_source_or_after_failed_exec_is_rejected():
    wrong = reduce_events(run(START, EXEC_OK, (T.REVIEWER_APPROVED, "Planner", {})))
    assert wrong.phase == "running" and "invalid_approval@3" in wrong.violations
    failed = reduce_events(run(START, EXEC_ERR, APPROVED))
    assert failed.phase == "running" and not failed.reviewer_verified


def test_terminal_states_are_mutually_exclusive():
    s = reduce_events(run(START, EXEC_OK, APPROVED, (T.LIMIT_REACHED, "app", {})))
    assert s.phase == "approved" and any("second_terminal" in v for v in s.violations)
    s2 = reduce_events(run(START, (T.RUN_ERROR, "app", {}), msg("Coder")))
    assert s2.phase == "error" and any("message_after_terminal" in v for v in s2.violations)


def test_human_approval_is_separate_and_only_after_terminal():
    early = reduce_events(run(START, (T.HUMAN_APPROVED, "human", {})))
    assert early.human == "none" and early.violations
    s = reduce_events(run(START, EXEC_OK, APPROVED, (T.HUMAN_APPROVED, "human", {})))
    assert s.reviewer_verified and s.human == "approved" and s.fully_verified
    rejected = reduce_events(run(START, EXEC_OK, APPROVED, (T.HUMAN_REJECTED, "human", {})))
    assert rejected.reviewer_verified and not rejected.fully_verified


def test_unapproved_run_never_fully_verified_even_with_human_approval():
    s = reduce_events(run(START, (T.LIMIT_REACHED, "app", {}), (T.HUMAN_APPROVED, "human", {})))
    assert s.phase == "limit_reached" and not s.fully_verified


def test_fault_injection_flag_and_usage_totals():
    s = reduce_events(
        run(
            START,
            (T.TEST_FAULT_INJECTED, "test_harness", {"kind": "rename_column"}),
            (T.USAGE, "Planner", {"input_tokens": 100, "output_tokens": 20}),
            (T.USAGE, "Coder", {"input_tokens": 50, "output_tokens": 70}),
        )
    )
    assert s.fault_injected and (s.input_tokens, s.output_tokens) == (150, 90)


def test_reducer_is_deterministic():
    evs = run(START, msg("Planner"), msg("Coder"), EXEC_OK)
    assert reduce_events(evs) == reduce_events(evs)


def test_chat_message_does_not_erase_real_result_status():
    s = reduce_events(run(START, EXEC_ERR, msg("Executor")))
    assert s.nodes["Executor"] == "error" and s.message_count == 1
    s2 = reduce_events(
        run(START, EXEC_OK, msg("Executor"), (T.REVIEW_FEEDBACK, "Reviewer", {}), msg("Reviewer"))
    )
    assert s2.nodes["Executor"] == "ok" and s2.nodes["Reviewer"] == "feedback"


def test_human_approval_requires_reviewer_approval_in_the_reducer_itself():
    forged = reduce_events(
        run(START, (T.LIMIT_REACHED, "app", {}), (T.HUMAN_APPROVED, "human", {}))
    )
    assert forged.human == "none" and any(
        "human_approval_without_reviewer" in v for v in forged.violations
    )
    errored = reduce_events(run(START, (T.RUN_ERROR, "app", {}), (T.HUMAN_APPROVED, "human", {})))
    assert errored.human == "none" and errored.violations


def test_duplicate_or_flipped_human_decisions_are_violations_and_do_not_change_state():
    base = (START, EXEC_OK, APPROVED)
    twice = reduce_events(
        run(*base, (T.HUMAN_APPROVED, "human", {}), (T.HUMAN_APPROVED, "human", {}))
    )
    assert twice.human == "approved" and any(
        "duplicate_human_decision" in v for v in twice.violations
    )
    flipped = reduce_events(
        run(*base, (T.HUMAN_APPROVED, "human", {}), (T.HUMAN_REJECTED, "human", {}))
    )
    assert flipped.human == "approved" and flipped.fully_verified
    back = reduce_events(
        run(*base, (T.HUMAN_REJECTED, "human", {}), (T.HUMAN_APPROVED, "human", {}))
    )
    assert back.human == "rejected" and not back.fully_verified


def test_a_follow_up_never_overwrites_a_human_decision():
    base = (START, EXEC_OK, APPROVED)
    approved = reduce_events(
        run(*base, (T.HUMAN_APPROVED, "human", {}), (T.HUMAN_FOLLOW_UP, "human", {}))
    )
    assert approved.human == "approved" and approved.fully_verified and approved.violations == ()
    asked = reduce_events(run(*base, (T.HUMAN_FOLLOW_UP, "human", {})))
    assert asked.human == "follow_up" and not asked.fully_verified
    later = reduce_events(
        run(*base, (T.HUMAN_FOLLOW_UP, "human", {}), (T.HUMAN_APPROVED, "human", {}))
    )
    assert later.human == "approved"

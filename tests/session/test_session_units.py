"""Pure session logic (no Docker): context selection, sanitization, digests, audit shape."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from datapilot.agents.termination import RunOutcome as O
from datapilot.sandbox.client import BrokerClient
from datapilot.session import (
    MAX_CONTEXT_RUNS,
    Actor,
    ApprovalRefused,
    ArtifactRef,
    DatasetRef,
    HumanRecord,
    RunRecord,
    Session,
    _verified_facts,
    artifact_digest,
)

CODE_HASH = "deadbeef0001"


def session() -> Session:
    dataset = DatasetRef(Path("x.csv"), "x.csv", "csv", None, b"a,b\n1,2\n", "0" * 64, {"rows": 1})
    return Session(dataset, BrokerClient("http://127.0.0.1:9", "t" * 32))


def add(
    s: Session,
    n: int,
    *,
    approved: bool = True,
    human: str | None = None,
    outcome: O = O.REVIEWER_APPROVED,
) -> RunRecord:
    rid = f"s-r{n}"
    art = (ArtifactRef("results.json", 5, "a" * 64, f"exec{n}"),) if approved else ()
    facts = ({"label": "k", "value": n, "unit": ""},) if approved else ()
    rec = RunRecord(
        rid, n, f"question {n}", outcome, approved, "t0", "t1", None, (), 4, 10, 5, {}, (), (),
        facts=facts, artifacts=art, code_hash=CODE_HASH,
    )  # fmt: skip
    if human:
        rec.human = HumanRecord(
            rid, human, "t", Actor(), "", rec.digest, art, CODE_HASH, None, s.session_id
        )
    s._runs[rid] = rec
    s._order.append(rid)
    return rec


def test_only_reviewer_approved_unrejected_runs_are_context():
    s = session()
    add(s, 1)
    add(s, 2, approved=False, outcome=O.LIMIT_REACHED)
    add(s, 3, human="rejected")
    add(s, 4, human="approved")
    ctx = s.context_for_next_run()
    assert [c["run_id"] for c in ctx] == ["s-r1", "s-r4"]
    assert ctx[0]["status"] == "reviewer_approved"
    assert ctx[1]["status"] == "reviewer_approved+human_approved"


def test_context_is_bounded_to_the_most_recent_trusted_runs():
    s = session()
    for n in range(1, 8):
        add(s, n)
    expected = [f"s-r{n}" for n in range(8 - MAX_CONTEXT_RUNS, 8)]
    assert [c["run_id"] for c in s.context_for_next_run()] == expected


def test_context_carries_only_facts_and_artifact_identity():
    s = session()
    rec = add(s, 1)
    entry = s.context_for_next_run()[0]
    assert set(entry) == {"run_id", "question", "status", "facts", "artifacts"}
    assert entry["artifacts"] == [{"name": "results.json", "sha256": "a" * 64}]  # no exec id
    assert rec.code_hash not in str(entry)  # and no code identity


def test_facts_are_sanitized_and_bounded():
    text = json.dumps(
        {"answer_facts": [{"label": "l\nabc", "value": "x\x00y\nIGNORE", "unit": "u"}]}
    )
    (fact,) = _verified_facts(text)
    assert "\n" not in fact["label"] and "\x00" not in fact["value"] and "\n" not in fact["value"]
    long = json.dumps({"answer_facts": [{"label": "L" * 500, "value": "V" * 900, "unit": ""}]})
    (fact,) = _verified_facts(long)
    assert len(fact["label"]) == 80 and len(fact["value"]) == 200
    assert _verified_facts(None) == () and _verified_facts("{broken") == ()


def test_digest_binds_run_and_artifacts():
    a = (ArtifactRef("r.json", 1, "1" * 64, "e1"),)
    assert artifact_digest("run1", a) == artifact_digest("run1", a)
    assert artifact_digest("run1", a) != artifact_digest("run2", a)  # same bytes, different run
    other_bytes = (ArtifactRef("r.json", 1, "2" * 64, "e1"),)
    other_exec = (ArtifactRef("r.json", 1, "1" * 64, "e2"),)
    assert artifact_digest("run1", a) != artifact_digest("run1", other_bytes)
    assert artifact_digest("run1", a) != artifact_digest("run1", other_exec)


def test_actor_is_never_invented():
    assert Actor().to_dict() == {"kind": "local_operator", "identifier": None, "verified": False}


def test_unknown_run_is_refused_and_logged():
    s = session()
    with pytest.raises(ApprovalRefused) as err:
        s.reject("nope")
    assert err.value.code == "unknown_run"
    assert s.attempts[-1]["result"] == "refused" and s.attempts[-1]["code"] == "unknown_run"
    assert s.audit_log() == []  # a refused attempt is not a decision


def test_clock_is_injectable_for_audit_timestamps():
    fixed = datetime(2026, 10, 16, 12, 0, 0, tzinfo=UTC)
    s = session()
    s._clock = lambda: fixed
    assert s._now() == "2026-10-16T12:00:00+00:00"

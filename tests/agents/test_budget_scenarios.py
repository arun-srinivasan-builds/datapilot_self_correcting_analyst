"""PRP §3.3 budget tables, reproduced as executable scenarios (real AutoGen teams, scripted LLM)."""

from __future__ import annotations

import pytest

from datapilot.agents.termination import RunOutcome as O
from tests.agents.helpers import run_script

A, L = O.REVIEWER_APPROVED, O.LIMIT_REACHED

ROUND_ROBIN = [
    ("clean pass", "P C E✓ R!", "PCER", 4, A),
    ("one exec error, then approved", "P C E✗ R P C E✓ R!", "PCERPCER", 8, A),
    ("PDF sample: error + feedback round", "P C E✗ R P C E✓ R P C E✓ R!", "PCERPCERPCER", 12, A),
    ("two feedback rounds", "P C E✓ R P C E✓ R P C E✓ R!", "PCERPCERPCER", 12, A),
    (
        "two exec errors + feedback: limit",
        "P C E✗ R P C E✗ R P C E✓ R P C E✓ R!",
        "PCERPCERPCER",
        12,
        L,
    ),
]
GUARDED = [
    ("clean pass", "P C E✓ R!", "PCER", 4, A),
    ("one exec error, then approved", "P C E✗ C E✓ R!", "PCECER", 6, A),
    ("exec error + feedback", "P C E✗ C E✓ R C E✓ R!", "PCECERCER", 9, A),
    ("two errors + feedback (11)", "P C E✗ C E✗ C E✓ R C E✓ R!", "PCECECERCER", 11, A),
    (
        "approved exactly on message 12",
        "P C E✓ R C E✓ R C E✗ C E✓ R!",
        "PCERCERCECER",
        12,
        A,
    ),
    (
        "three errors + feedback: limit",
        "P C E✗ C E✗ C E✗ C E✓ R C E✓ R!",
        "PCECECECER" + "CE",
        12,
        L,
    ),
]


@pytest.mark.parametrize(("name", "script", "letters", "count", "outcome"), ROUND_ROBIN)
async def test_round_robin_budget_table(name, script, letters, count, outcome):
    run = await run_script(script, "round_robin")
    assert run.letters == letters, name
    assert run.canvas.message_count == count
    assert run.outcome is outcome
    assert run.canvas.violations == ()


@pytest.mark.parametrize(("name", "script", "letters", "count", "outcome"), GUARDED)
async def test_guarded_selector_budget_table(name, script, letters, count, outcome):
    run = await run_script(script, "selector")
    assert run.letters == letters, name
    assert run.canvas.message_count == count
    assert run.outcome is outcome
    assert run.canvas.violations == ()
    # guarded routing never fell back to the selector LLM (its replay client has no responses)
    assert run.selector.total_usage().prompt_tokens == 0


async def test_limit_run_is_unapproved_and_cannot_be_human_approved():
    run = await run_script("P C E✗ C E✗ C E✗ C E✓ R C E✓ R!")
    canvas = run.canvas
    assert canvas.phase == "limit_reached"
    assert not canvas.reviewer_verified and not canvas.fully_verified
    assert run.of("reviewer_approved") == []
    limit = run.of("limit_reached")[0]
    assert limit.payload["limit"] == "messages" and limit.payload["count"] == 12

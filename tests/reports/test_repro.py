"""Reproducibility verdict logic (offline: a stub backend returns canned execution results)."""

from __future__ import annotations

import json

from datapilot.reports.repro import verify_reproducible
from datapilot.sandbox.contracts import ExecutionResult

ORIGINAL = json.dumps({"answer_facts": [{"label": "a", "value": 1, "unit": ""}]})


class Stub:
    def __init__(self, result: ExecutionResult) -> None:
        self.result, self.calls = result, []

    async def run(self, code: str, *, run_id: str) -> ExecutionResult:
        self.calls.append((code, run_id))
        return self.result


async def test_identical_facts_are_reproducible_even_if_key_order_differs() -> None:
    again = json.dumps({"charts": [], "answer_facts": [{"unit": "", "value": 1, "label": "a"}]})
    stub = Stub(ExecutionResult("ok", 0, results_json=again))
    out = await verify_reproducible("code", ORIGINAL, stub, run_id="r1")
    assert out.reproducible and stub.calls == [("code", "r1-repro")]


async def test_different_facts_are_not_reproducible() -> None:
    other = json.dumps({"answer_facts": [{"label": "a", "value": 2, "unit": ""}]})
    out = await verify_reproducible(
        "c", ORIGINAL, Stub(ExecutionResult("ok", 0, results_json=other)), run_id="r"
    )
    assert not out.reproducible and "differ" in out.reason


async def test_failed_reexecution_is_not_reproducible() -> None:
    out = await verify_reproducible("c", ORIGINAL, Stub(ExecutionResult("error", 1)), run_id="r")
    assert not out.reproducible and "failed" in out.reason


async def test_missing_results_is_not_reproducible() -> None:
    out = await verify_reproducible("c", ORIGINAL, Stub(ExecutionResult("ok", 0)), run_id="r")
    assert not out.reproducible

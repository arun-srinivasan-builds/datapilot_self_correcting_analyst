"""Reproducibility check for an exported `analysis.py` (PRP M5 step 2).

The approved script is executed again in a brand-new sandbox container against the same dataset
bytes. It is reproducible when the run succeeds and its `results.json` carries exactly the same
answer facts as the original run. Nothing here asks a model anything.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from datapilot.sandbox.contracts import ExecutionBackend, ExecutionResult


@dataclass(frozen=True, slots=True)
class Reproducibility:
    reproducible: bool
    reason: str
    original_sha256: str | None
    rerun_sha256: str | None
    rerun: ExecutionResult | None = None


def _canonical_facts(results_json: str | None) -> str | None:
    if results_json is None:
        return None
    try:
        data = json.loads(results_json)
    except ValueError:
        return None
    facts = data.get("answer_facts") if isinstance(data, dict) else None
    return json.dumps(facts, sort_keys=True, ensure_ascii=False) if facts is not None else None


def _digest(text: str | None) -> str | None:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text is not None else None


async def verify_reproducible(
    code: str, original_results_json: str, backend: ExecutionBackend, *, run_id: str
) -> Reproducibility:
    """Re-execute `code` once and compare the answer facts with the original run's."""
    original = _canonical_facts(original_results_json)
    result = await backend.run(code, run_id=f"{run_id}-repro")
    rerun = _canonical_facts(result.results_json)
    o_hash, r_hash = _digest(original), _digest(rerun)
    if not result.ok:
        return Reproducibility(
            False, f"re-execution failed ({result.status}, exit {result.exit_code})", o_hash, None,
            result,
        )  # fmt: skip
    if original is None or rerun is None:
        return Reproducibility(
            False, "answer_facts missing in one of the runs", o_hash, r_hash, result
        )
    if original != rerun:
        return Reproducibility(False, "answer facts differ between runs", o_hash, r_hash, result)
    return Reproducibility(True, "identical answer facts on re-execution", o_hash, r_hash, result)

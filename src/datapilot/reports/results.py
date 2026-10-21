"""Minimal `results.json` contract (PRP §4.4, Stage 5 subset).

Schema:  {"answer_facts": [{"label": str, "value": number | str, "unit": str}, ...],
          "charts": [{"file": str, "title": str, "x_label": str, "y_label": str, "unit": str}, ...]}
Checks here are structural and internal-consistency only. Chart quality, number-vs-narrative checks
and exports belong to M5. Correctness of the analysis itself is checked by evals against ground
truth, never by this module.
"""

from __future__ import annotations

import json
import math
from collections.abc import Collection

MAX_FACTS = 200
MAX_CATEGORIES = 60
MAX_SERIES = 6
CHART_FIELDS = ("file", "title", "x_label", "y_label", "unit")


def validate_results(text: str | None, artifact_names: Collection[str]) -> list[str]:
    """Return human-readable violations (empty list = contract satisfied)."""
    if text is None:
        return ["results.json was not produced in OUTPUT_DIR"]
    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except ValueError as exc:
        return [f"results.json is not valid JSON: {exc}"]
    if not isinstance(data, dict):
        return ["results.json must be a JSON object"]
    problems: list[str] = []
    facts = data.get("answer_facts")
    if not isinstance(facts, list) or not facts:
        problems.append("'answer_facts' must be a non-empty list")
    else:
        problems += _check_facts(facts)
    charts = data.get("charts", [])
    if not isinstance(charts, list):
        problems.append("'charts' must be a list")
    else:
        problems += _check_charts(charts, set(artifact_names))
    return problems


def _reject_constant(name: str) -> float:
    raise ValueError(f"{name} is not allowed")


def _check_facts(facts: list[object]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    if len(facts) > MAX_FACTS:
        problems.append(f"too many answer_facts ({len(facts)} > {MAX_FACTS})")
    for i, fact in enumerate(facts[:MAX_FACTS]):
        if not isinstance(fact, dict):
            problems.append(f"answer_facts[{i}] must be an object")
            continue
        label, value, unit = fact.get("label"), fact.get("value"), fact.get("unit")
        if not isinstance(label, str) or not label.strip():
            problems.append(f"answer_facts[{i}].label must be a non-empty string")
        elif label in seen:
            problems.append(f"answer_facts[{i}].label '{label}' is duplicated")
        else:
            seen.add(label)
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            problems.append(f"answer_facts[{i}].value must be a number or string")
        elif isinstance(value, float) and not math.isfinite(value):
            problems.append(f"answer_facts[{i}].value must be finite")
        elif isinstance(value, str) and not value.strip():
            problems.append(f"answer_facts[{i}].value must not be empty")
        if not isinstance(unit, str):
            problems.append(f"answer_facts[{i}].unit must be a string (use '' for none)")
    return problems


def _check_charts(charts: list[object], artifacts: set[str]) -> list[str]:
    problems: list[str] = []
    for i, chart in enumerate(charts):
        if not isinstance(chart, dict):
            problems.append(f"charts[{i}] must be an object")
            continue
        for field in CHART_FIELDS:
            if not isinstance(chart.get(field), str):
                problems.append(f"charts[{i}].{field} must be a string")
        file = chart.get("file")
        if isinstance(file, str) and file not in artifacts:
            problems.append(f"charts[{i}].file '{file}' was not written to OUTPUT_DIR")
        if "data" in chart:
            problems += _check_chart_data(i, chart["data"])
    return problems


def _check_chart_data(i: int, data: object) -> list[str]:
    """Optional machine-readable series behind a chart (lets a UI redraw it natively)."""
    where = f"charts[{i}].data"
    if not isinstance(data, dict):
        return [f"{where} must be an object"]
    cats, series = data.get("categories"), data.get("series")
    if not isinstance(cats, list) or not 1 <= len(cats) <= MAX_CATEGORIES:
        return [f"{where}.categories must be a list of 1-{MAX_CATEGORIES} labels"]
    if not all(isinstance(c, str) and c.strip() for c in cats):
        return [f"{where}.categories must be non-empty strings"]
    if not isinstance(series, list) or not 1 <= len(series) <= MAX_SERIES:
        return [f"{where}.series must be a list of 1-{MAX_SERIES} series"]
    problems: list[str] = []
    for j, s in enumerate(series):
        values = s.get("values") if isinstance(s, dict) else None
        if not isinstance(s, dict) or not isinstance(s.get("name"), str):
            problems.append(f"{where}.series[{j}] needs a string name")
        elif not isinstance(values, list) or len(values) != len(cats):
            problems.append(f"{where}.series[{j}].values must match categories in length")
        elif not all(
            isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)
            for v in values
        ):
            problems.append(f"{where}.series[{j}].values must be finite numbers")
    return problems

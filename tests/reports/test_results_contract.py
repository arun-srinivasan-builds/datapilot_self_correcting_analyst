from __future__ import annotations

import json

import pytest

from datapilot.reports.results import validate_results

GOOD = {
    "answer_facts": [
        {"label": "biggest_drop_category", "value": "Electronics", "unit": ""},
        {"label": "biggest_drop_amount", "value": -3980399.85, "unit": "INR"},
    ],
    "charts": [
        {"file": "c.png", "title": "t", "x_label": "x", "y_label": "y", "unit": "INR"},
    ],
}


def check(data, names=("c.png", "results.json")):
    return validate_results(json.dumps(data) if not isinstance(data, str) else data, names)


def test_a_valid_document_has_no_violations():
    assert check(GOOD) == []
    assert check({"answer_facts": GOOD["answer_facts"]}) == []  # charts are optional


def test_missing_file_and_invalid_json_are_reported():
    assert "not produced" in validate_results(None, [])[0]
    assert "not valid JSON" in check("{broken")[0]
    assert (
        "NaN is not allowed"
        in check('{"answer_facts": [{"label": "a", "value": NaN, "unit": ""}]}')[0]
    )
    assert (
        "Infinity" in check('{"answer_facts": [{"label": "a", "value": Infinity, "unit": ""}]}')[0]
    )
    assert "JSON object" in check("[1]")[0]


@pytest.mark.parametrize(
    ("patch", "needle"),
    [
        ({"answer_facts": []}, "non-empty list"),
        ({"answer_facts": "x"}, "non-empty list"),
        ({"answer_facts": [5]}, "must be an object"),
        ({"answer_facts": [{"label": "", "value": 1, "unit": ""}]}, "label"),
        ({"answer_facts": [{"label": "a", "value": None, "unit": ""}]}, "number or string"),
        ({"answer_facts": [{"label": "a", "value": True, "unit": ""}]}, "number or string"),
        ({"answer_facts": [{"label": "a", "value": " ", "unit": ""}]}, "must not be empty"),
        ({"answer_facts": [{"label": "a", "value": 1}]}, "unit"),
        (
            {
                "answer_facts": [
                    {"label": "a", "value": 1, "unit": ""},
                    {"label": "a", "value": 2, "unit": ""},
                ]
            },
            "duplicated",
        ),
        ({"charts": "x"}, "must be a list"),
        ({"charts": [{"file": "c.png"}]}, "title"),
        (
            {
                "charts": [
                    {
                        "file": "missing.png",
                        "title": "t",
                        "x_label": "x",
                        "y_label": "y",
                        "unit": "",
                    }
                ]
            },
            "was not written",
        ),
    ],
)
def test_each_contract_violation_is_reported(patch, needle):
    problems = check({**GOOD, **patch})
    assert any(needle in p for p in problems), problems


def test_oversized_fact_list_is_bounded():
    many = {"answer_facts": [{"label": f"l{i}", "value": i, "unit": ""} for i in range(500)]}
    assert any("too many" in p for p in check(many))

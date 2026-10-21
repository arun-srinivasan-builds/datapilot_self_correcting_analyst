"""One-page PDF: built from real evidence of the live fault-injection demo (offline, no model)."""

from __future__ import annotations

import json
from pathlib import Path

from datapilot.reports.pdf import ChartImage, build_pdf, page_count

EVIDENCE = Path(__file__).resolve().parents[2] / "docs" / "evidence" / "m3" / "fault-injection"


def _report(n_facts: int | None = None, n_charts: int = 3) -> bytes:
    results = json.loads((EVIDENCE / "results.json").read_text(encoding="utf-8"))
    charts = [
        ChartImage(c["title"], (EVIDENCE / c["file"]).read_bytes()) for c in results["charts"]
    ][:n_charts]
    return build_pdf(
        question="Which category had the biggest revenue drop?",
        facts=results["answer_facts"][:n_facts],
        charts=charts,
        reviewer_status="Approved",
        human_status="Pending",
        run_id="test-run",
        dataset_name="sales_sample.csv",
        messages=6,
    )


def test_pdf_is_a_single_page_pdf():
    pdf = _report()
    assert pdf.startswith(b"%PDF")
    assert page_count(pdf) == 1


def test_pdf_stays_one_page_with_many_facts_and_hostile_text():
    results = json.loads((EVIDENCE / "results.json").read_text(encoding="utf-8"))
    facts = [{"label": "<b>x</b>&" * 30, "value": "v" * 500, "unit": "u"}] * 60
    pdf = build_pdf(
        question="q" * 5000,
        facts=facts + results["answer_facts"],
        charts=[],
        reviewer_status="Approved",
        human_status="Rejected",
        run_id="r",
        dataset_name="<script>.csv",
        messages=12,
    )
    assert page_count(pdf) == 1


def test_pdf_without_charts_or_facts_still_builds():
    pdf = build_pdf(
        question="q", facts=[], charts=[], reviewer_status="Unapproved", human_status="—",
        run_id="r", dataset_name="d.csv", messages=0,
    )  # fmt: skip
    assert page_count(pdf) == 1

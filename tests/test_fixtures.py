from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from fixtures import generate

ROOT = Path(__file__).resolve().parents[1]


def test_sample_has_pdf_shape_and_row_count(fx):
    df = pd.read_csv(fx["sample"])
    assert len(df) == 12_480
    assert list(df.columns) == [
        "order_date",
        "region",
        "category",
        "product",
        "units",
        "unit_price",
        "discount",
    ]
    assert df.isna().sum().sum() == 0


def test_generation_is_reproducible(fx, tmp_path):
    again = generate.generate_all(tmp_path)
    for key in ("sample", "alt", "sample_truth", "alt_truth"):
        assert again[key].read_bytes() == fx[key].read_bytes(), key
    a = pd.read_excel(fx["multisheet"], sheet_name=None)
    b = pd.read_excel(again["multisheet"], sheet_name=None)
    assert a.keys() == b.keys()
    for name in a:
        pd.testing.assert_frame_equal(a[name], b[name])


def test_committed_fixtures_match_generator(fx):
    for key in ("sample", "alt", "sample_truth", "alt_truth"):
        committed = ROOT / "fixtures" / fx[key].name
        assert committed.read_bytes() == fx[key].read_bytes(), f"regenerate {committed.name}"


def test_truth_is_independently_verified_and_unambiguous(fx):
    df = pd.read_csv(fx["sample"])
    df["rev"] = df.units * df.unit_price * (1 - df.discount)
    df["m"] = df.order_date.str[:7]
    piv = df.pivot_table(index="category", columns="m", values="rev", aggfunc="sum")
    change = (piv["2026-09"] - piv["2026-08"]).sort_values()
    truth = json.loads(fx["sample_truth"].read_text())
    assert truth["biggest_drop_category"] == change.index[0] == "Electronics"
    assert truth["top_region_for_that_drop"] == "South"
    assert change.iloc[0] < change.iloc[1] * 2  # clear, not marginal, vs runner-up
    assert abs(truth["total_revenue"] - round(df.rev.sum(), 2)) < 0.01


def test_alt_schema_differs_and_has_quality_issues(fx):
    alt = pd.read_csv(fx["alt"])
    sample = pd.read_csv(fx["sample"])
    assert not set(alt.columns) & set(sample.columns)
    truth = json.loads(fx["alt_truth"].read_text())
    assert alt.net_amount.isna().sum() == truth["null_net_amount"] > 0
    assert alt.duplicated().sum() == truth["duplicate_rows"] == 10


def test_multisheet_workbook(fx):
    sheets = pd.read_excel(fx["multisheet"], sheet_name=None)
    assert list(sheets) == ["Orders", "Returns", "Targets"]
    assert len(sheets["Orders"]) == 600
    assert "refund_amount" in sheets["Returns"].columns

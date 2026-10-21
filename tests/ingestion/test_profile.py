from __future__ import annotations

from datapilot.ingestion import load_dataset, profile_frame, sample_rows


def test_sample_profile(fx):
    prof = profile_frame(load_dataset(fx["sample"]).frame)
    assert prof.rows == 12_480
    assert prof.date_columns == ("order_date",)
    by = {c.name: c for c in prof.columns}
    assert by["units"].logical_type == "integer"
    assert by["discount"].logical_type == "float"
    assert by["region"].logical_type == "text"
    assert by["region"].unique == 4
    assert by["unit_price"].minimum == 149.0
    assert not any(f.code == "missing_values" for f in prof.quality_flags)


def test_alt_profile_flags_quality_issues_and_detects_text_dates(fx):
    prof = profile_frame(load_dataset(fx["alt"]).frame)
    assert prof.date_columns == ("txn_date",)
    codes = {f.code for f in prof.quality_flags}
    assert {"missing_values", "duplicate_rows"} <= codes
    assert prof.duplicate_rows == 10
    nulls = {c.name: c.nulls for c in prof.columns}
    assert nulls["net_amount"] == 64 and nulls["branch"] == 33


def test_multisheet_profiles_per_sheet(fx):
    returns = profile_frame(load_dataset(fx["multisheet"], "Returns").frame)
    assert returns.date_columns == ("return_date",)
    targets = profile_frame(load_dataset(fx["multisheet"], "Targets").frame)
    assert targets.rows == 16


def test_prompt_dict_is_compact_and_data_only(fx):
    ds = load_dataset(fx["sample"])
    prof = profile_frame(ds.frame)
    d = prof.to_prompt_dict(sample_rows(ds.frame, 5))
    assert len(d["sample_rows"]) == 5
    assert d["rows"] == 12_480 and len(d["columns"]) == 7
    assert all(len(c["sample"]) <= 3 for c in d["columns"])


def test_numeric_ids_are_not_dates(tmp_path):
    p = tmp_path / "ids.csv"
    p.write_text("order_id,amount\n" + "\n".join(f"{20260000 + i},{i}.5" for i in range(50)))
    prof = profile_frame(load_dataset(p).frame)
    assert prof.date_columns == ()

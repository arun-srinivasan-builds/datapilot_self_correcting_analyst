from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from datapilot.ingestion import IngestionError, list_sheets, load_dataset


def code_of(fn, *a, **k) -> str:
    with pytest.raises(IngestionError) as ei:
        fn(*a, **k)
    return ei.value.code


def test_load_csv(fx):
    ds = load_dataset(fx["sample"])
    assert ds.frame.shape == (12_480, 7)
    assert ds.sheet is None and ds.sheets == ()
    assert len(ds.fingerprint) == 64


def test_load_multisheet_and_select(fx):
    assert list_sheets(fx["multisheet"]) == ("Orders", "Returns", "Targets")
    default = load_dataset(fx["multisheet"])
    assert default.sheet == "Orders" and len(default.frame) == 600
    returns = load_dataset(fx["multisheet"], "Returns")
    assert returns.sheet == "Returns" and len(returns.frame) == 150
    assert returns.fingerprint != default.fingerprint


def test_unknown_sheet(fx):
    assert code_of(load_dataset, fx["multisheet"], "Nope") == "unknown_sheet"


def test_unsupported_extension(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("a,b\n1,2\n")
    assert code_of(load_dataset, p) == "unsupported_type"


def test_empty_and_header_only(tmp_path):
    e = tmp_path / "e.csv"
    e.write_bytes(b"")
    assert code_of(load_dataset, e) == "empty_file"
    h = tmp_path / "h.csv"
    h.write_text("a,b,c\n")
    assert code_of(load_dataset, h) == "empty_data"


def test_oversize(tmp_path):
    p = tmp_path / "big.csv"
    p.write_text("a,b\n" + "1,2\n" * 400_000)  # ~1.6 MB
    assert code_of(load_dataset, p, max_upload_mb=1) == "too_large"


def test_magic_bytes(tmp_path):
    fake_xlsx = tmp_path / "x.xlsx"
    fake_xlsx.write_text("a,b\n1,2\n")
    assert code_of(load_dataset, fake_xlsx) == "bad_content"
    fake_csv = tmp_path / "x.csv"
    with zipfile.ZipFile(fake_csv, "w") as zf:
        zf.writestr("a.txt", "x")
    assert code_of(load_dataset, fake_csv) == "bad_content"


def test_duplicate_columns(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("a,b,A\n1,2,3\n")
    assert code_of(load_dataset, p) == "duplicate_columns"


def test_row_and_column_caps(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text("a,b\n" + "1,2\n" * 50)
    assert code_of(load_dataset, p, max_rows=10) == "too_many_rows"
    assert code_of(load_dataset, p, max_columns=1) == "too_many_columns"


def _zip_xlsx(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def test_macro_workbook_rejected(tmp_path):
    p = tmp_path / "m.xlsx"
    _zip_xlsx(p, {"xl/workbook.xml": b"<x/>", "xl/vbaProject.bin": b"\x00"})
    assert code_of(load_dataset, p) == "macros"


def test_zip_bomb_rejected(tmp_path):
    p = tmp_path / "z.xlsx"
    _zip_xlsx(p, {"xl/workbook.xml": b"<x/>", "xl/big.bin": b"\x00" * 50_000_000})
    assert code_of(load_dataset, p) == "zip_bomb"


def test_non_workbook_zip_rejected(tmp_path):
    p = tmp_path / "n.xlsx"
    _zip_xlsx(p, {"hello.txt": b"hi"})
    assert code_of(load_dataset, p) == "bad_content"


def test_semicolon_delimiter_and_latin1(tmp_path):
    p = tmp_path / "s.csv"
    p.write_bytes("name;amount\ncafé;10\nbar;20\n".encode("cp1252"))
    ds = load_dataset(p)
    assert list(ds.frame.columns) == ["name", "amount"]
    assert ds.frame["name"].iloc[0] == "café"

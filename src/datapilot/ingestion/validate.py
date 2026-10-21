"""Pre-parse validation of uploaded files. Uploaded files are untrusted."""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

from datapilot.ingestion.models import IngestionError

ALLOWED_SUFFIXES = {".csv", ".xlsx"}
XLSX_MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
XLSX_MAX_RATIO = 100
XLSX_MAX_MEMBERS = 500
_CSV_ENCODINGS = ("utf-8-sig", "cp1252")


def check_file(path: Path, max_upload_mb: int) -> str:
    """Validate extension, size, and magic bytes. Returns the kind: 'csv' or 'xlsx'."""
    suffix = path.suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise IngestionError(
            "unsupported_type", f"Unsupported file type '{suffix}'. Use CSV or XLSX."
        )
    if not path.is_file():
        raise IngestionError("not_found", "The file does not exist.")
    size = path.stat().st_size
    if size == 0:
        raise IngestionError("empty_file", "The file is empty.")
    if size > max_upload_mb * 1024 * 1024:
        raise IngestionError("too_large", f"The file is larger than the {max_upload_mb} MB limit.")
    with path.open("rb") as fh:
        head = fh.read(4096)
    if suffix == ".xlsx":
        if not head.startswith(b"PK\x03\x04"):
            raise IngestionError("bad_content", "The file is not a valid XLSX workbook.")
        _check_zip(path)
        return "xlsx"
    if head.startswith(b"PK\x03\x04") or b"\x00" in head:
        raise IngestionError("bad_content", "The file does not look like a text CSV.")
    return "csv"


def _check_zip(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            names = [i.filename.lower() for i in infos]
            if len(infos) > XLSX_MAX_MEMBERS:
                raise IngestionError("zip_bomb", "The workbook has too many internal parts.")
            total = sum(i.file_size for i in infos)
            if total > XLSX_MAX_UNCOMPRESSED_BYTES:
                raise IngestionError("zip_bomb", "The workbook expands to an unsafe size.")
            packed = max(sum(i.compress_size for i in infos), 1)
            if total / packed > XLSX_MAX_RATIO:
                raise IngestionError("zip_bomb", "The workbook compression ratio is unsafe.")
            if any("vbaproject" in n for n in names):
                raise IngestionError("macros", "Workbooks containing macros are not accepted.")
            if "xl/workbook.xml" not in names:
                raise IngestionError("bad_content", "The file is not a valid XLSX workbook.")
    except zipfile.BadZipFile as exc:
        raise IngestionError("bad_content", "The file is not a valid XLSX workbook.") from exc


def has_external_links(path: Path) -> bool:
    with zipfile.ZipFile(path) as zf:
        return any(n.lower().startswith("xl/externallinks/") for n in zf.namelist())


def sniff_csv(path: Path) -> tuple[str, str]:
    """Return (encoding, delimiter). Rejects files that cannot be decoded as text."""
    raw = path.read_bytes()[:65536]
    for enc in _CSV_ENCODINGS:
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        try:
            dialect = csv.Sniffer().sniff(text.split("\n", 1)[0] or ",", delimiters=",;\t|")
            return enc, dialect.delimiter
        except csv.Error:
            return enc, ","
    raise IngestionError("bad_encoding", "The CSV text encoding is not supported.")


def check_header(columns: list[object]) -> None:
    names = [str(c).strip() for c in columns]
    if not names or all(not n or n.lower().startswith("unnamed") for n in names):
        raise IngestionError("no_header", "No header row was found.")
    seen: set[str] = set()
    dups: list[str] = []
    for n in names:
        key = n.lower()
        if key in seen:
            dups.append(n)
        seen.add(key)
    if dups:
        raise IngestionError(
            "duplicate_columns", f"Duplicate column names: {', '.join(sorted(set(dups)))}."
        )


def header_of_csv(path: Path, encoding: str, delimiter: str) -> list[str]:
    with path.open("r", encoding=encoding, newline="") as fh:
        first = next(csv.reader(io.StringIO(fh.readline()), delimiter=delimiter), [])
    return first

"""Dataset profiling: types, nulls, date detection, quality flags. Schema-agnostic."""

from __future__ import annotations

import warnings

import pandas as pd
from pandas.api import types as pdt

from datapilot.ingestion.models import (
    ColumnProfile,
    DatasetProfile,
    LogicalType,
    QualityFlag,
)

DATE_PARSE_THRESHOLD = 0.9
HIGH_NULL_PCT = 20.0
SAMPLE_SIZE = 3


def _looks_like_dates(series: pd.Series) -> bool:
    values = series.dropna().astype(str).str.strip()
    if values.empty or values.str.fullmatch(r"-?\d+(\.\d+)?").mean() > 0.5:
        return False
    probe = values.head(500)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(probe, errors="coerce", format="mixed")
    return float(parsed.notna().mean()) >= DATE_PARSE_THRESHOLD


def _logical_type(series: pd.Series) -> LogicalType:
    if pdt.is_bool_dtype(series):
        return "boolean"
    if pdt.is_datetime64_any_dtype(series):
        return "datetime"
    if pdt.is_integer_dtype(series):
        return "integer"
    if pdt.is_numeric_dtype(series):
        return "float"
    return "datetime" if _looks_like_dates(series) else "text"


def _sample(series: pd.Series) -> tuple[str, ...]:
    return tuple(str(v) for v in series.dropna().unique()[:SAMPLE_SIZE])


def profile_frame(df: pd.DataFrame) -> DatasetProfile:
    rows = len(df)
    columns: list[ColumnProfile] = []
    flags: list[QualityFlag] = []
    for name in df.columns:
        s = df[name]
        ltype = _logical_type(s)
        nulls = int(s.isna().sum())
        numeric = ltype in ("integer", "float") and not pdt.is_bool_dtype(s)
        columns.append(
            ColumnProfile(
                name=str(name),
                logical_type=ltype,
                dtype=str(s.dtype),
                nulls=nulls,
                null_pct=round(100.0 * nulls / rows, 2) if rows else 0.0,
                unique=int(s.nunique(dropna=True)),
                sample=_sample(s),
                minimum=float(s.min()) if numeric and nulls < rows else None,
                maximum=float(s.max()) if numeric and nulls < rows else None,
                mean=round(float(s.mean()), 4) if numeric and nulls < rows else None,
            )
        )
    with_nulls = tuple(c.name for c in columns if c.nulls)
    if with_nulls:
        flags.append(
            QualityFlag(
                "missing_values",
                "warning",
                f"{len(with_nulls)} column(s) have missing values.",
                with_nulls,
            )
        )
    high = tuple(c.name for c in columns if c.null_pct >= HIGH_NULL_PCT)
    if high:
        flags.append(
            QualityFlag(
                "high_null_rate",
                "warning",
                f"Over {HIGH_NULL_PCT:.0f}% missing in: {', '.join(high)}.",
                high,
            )
        )
    const = tuple(c.name for c in columns if c.unique <= 1 and rows > 1)
    if const:
        flags.append(QualityFlag("constant_column", "info", "Constant column(s).", const))
    dups = int(df.duplicated().sum())
    if dups:
        flags.append(QualityFlag("duplicate_rows", "warning", f"{dups} duplicate row(s)."))
    date_cols = tuple(c.name for c in columns if c.logical_type == "datetime")
    if not date_cols:
        flags.append(QualityFlag("no_date_column", "info", "No date column was detected."))
    return DatasetProfile(
        rows=rows,
        columns=tuple(columns),
        date_columns=date_cols,
        duplicate_rows=dups,
        quality_flags=tuple(flags),
    )


def sample_rows(df: pd.DataFrame, n: int = 5) -> list[dict[str, object]]:
    """First `n` rows as plain dicts (strings), for the delimited data section of a prompt."""
    return [
        {str(k): ("" if pd.isna(v) else str(v)) for k, v in row.items()}
        for row in df.head(n).to_dict(orient="records")
    ]

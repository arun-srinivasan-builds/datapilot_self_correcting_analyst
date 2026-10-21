"""Immutable ingestion result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd

Severity = Literal["info", "warning", "error"]
LogicalType = Literal["integer", "float", "boolean", "datetime", "text"]


class IngestionError(Exception):
    """A file was rejected. `code` is stable and safe to show to users."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ColumnProfile:
    name: str
    logical_type: LogicalType
    dtype: str
    nulls: int
    null_pct: float
    unique: int
    sample: tuple[str, ...]
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None


@dataclass(frozen=True, slots=True)
class QualityFlag:
    code: str
    severity: Severity
    message: str
    columns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DatasetProfile:
    rows: int
    columns: tuple[ColumnProfile, ...]
    date_columns: tuple[str, ...]
    duplicate_rows: int
    quality_flags: tuple[QualityFlag, ...]

    def to_prompt_dict(self, sample_rows: list[dict[str, Any]]) -> dict[str, Any]:
        """Compact, data-only profile for the Planner (no raw dataset dump)."""
        return {
            "rows": self.rows,
            "columns": [
                {
                    "name": c.name,
                    "type": c.logical_type,
                    "nulls": c.nulls,
                    "unique": c.unique,
                    "sample": list(c.sample),
                }
                for c in self.columns
            ],
            "date_columns": list(self.date_columns),
            "duplicate_rows": self.duplicate_rows,
            "quality_flags": [f.code for f in self.quality_flags],
            "sample_rows": sample_rows,
        }


@dataclass(frozen=True, slots=True, eq=False)
class Dataset:
    frame: pd.DataFrame = field(repr=False)
    name: str
    sheet: str | None
    sheets: tuple[str, ...]
    fingerprint: str
    size_bytes: int

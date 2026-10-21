"""Session state and dataset loading for the Streamlit UI (path + profile only, no raw frames in state)."""

from __future__ import annotations

import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

from datapilot.config import Settings, get_settings
from datapilot.ingestion import Dataset, DatasetProfile, IngestionError, list_sheets, load_dataset
from datapilot.ingestion.profile import profile_frame

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "fixtures"
WORKSPACES = ("explore", "livewire", "insights")
# widget keys kept alive when their workspace is not rendered (Streamlit drops unrendered widgets)
PERSIST = ("q", "mode", "sample", "sheet", "preview_pick", "inspector")


@dataclass(frozen=True)
class Loaded:
    dataset: Dataset
    profile: DatasetProfile
    date_ranges: dict[str, tuple[str, str]]


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("ws", "explore")
    ss.setdefault("session_id", uuid.uuid4().hex[:12])
    ss.setdefault("source", None)  # {"kind": "upload"|"sample", "name": str, "path": str}
    ss.setdefault("preview_key", None)
    ss.setdefault("human", None)
    ss.setdefault("followup_note", None)
    for key in PERSIST:  # keep widget state across workspace switches
        if key in ss:
            ss[key] = ss[key]


def session_dir() -> Path:
    path = Path(tempfile.gettempdir()) / "datapilot" / st.session_state["session_id"]
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name)[:80] or "upload"


def sample_files() -> list[Path]:
    if not FIXTURES.is_dir():
        return []
    return sorted(p for p in FIXTURES.iterdir() if p.suffix.lower() in (".csv", ".xlsx"))


@st.cache_resource(show_spinner=False, max_entries=6)
def _load_cached(
    path: str, mtime: float, sheet: str | None, max_mb: int, max_rows: int, max_cols: int
) -> Loaded:
    del mtime  # part of the cache key only
    dataset = load_dataset(
        Path(path), sheet, max_upload_mb=max_mb, max_rows=max_rows, max_columns=max_cols
    )
    profile = profile_frame(dataset.frame)
    ranges: dict[str, tuple[str, str]] = {}
    for col in profile.date_columns:
        parsed = pd.to_datetime(dataset.frame[col], errors="coerce", format="mixed")
        if parsed.notna().any():
            ranges[col] = (str(parsed.min().date()), str(parsed.max().date()))
    return Loaded(dataset, profile, ranges)


def load_current(sheet: str | None) -> tuple[Loaded | None, str | None]:
    """Load the active source. Returns (loaded, error_message); never raises for bad files."""
    src = st.session_state.get("source")
    if not src:
        return None, None
    s: Settings = get_settings()
    path = Path(src["path"])
    try:
        mtime = path.stat().st_mtime
        return _load_cached(
            str(path), mtime, sheet, s.max_upload_mb, s.max_rows, s.max_columns
        ), None
    except IngestionError as exc:
        return None, f"{exc.message} ({exc.code})"
    except OSError:
        return None, "The dataset file is no longer available. Please select it again."


def sheets_for_current() -> tuple[str, ...]:
    src = st.session_state.get("source")
    if not src or not str(src["path"]).lower().endswith(".xlsx"):
        return ()
    try:
        return list_sheets(Path(src["path"]), get_settings().max_upload_mb)
    except IngestionError:
        return ()

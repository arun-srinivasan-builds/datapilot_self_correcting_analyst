"""Ask & Explore: data source, profile + preview, question composer. Real ingestion; starts real runs."""

from __future__ import annotations

from html import escape
from pathlib import Path

import streamlit as st

from datapilot.ingestion import IngestionError
from datapilot.ingestion.profile import sample_rows
from datapilot.ui import markup as h
from datapilot.ui.chrome import common_chips
from datapilot.ui.demo import is_demo
from datapilot.ui.live import LiveUnavailableError, get_live, readiness
from datapilot.ui.state import (
    Loaded,
    load_current,
    safe_name,
    sample_files,
    session_dir,
    sheets_for_current,
)

_NUMERIC = ("integer", "float")
_MEASURE_HINTS = (
    "revenue",
    "amount",
    "sales",
    "price",
    "total",
    "value",
    "cost",
    "units",
    "qty",
    "quantity",
)


def suggestions(loaded: Loaded) -> list[str]:
    """Schema-driven suggestions: derived from the profile, never hardcoded to a sample schema."""
    cols = loaded.profile.columns
    nums = [c.name for c in cols if c.logical_type in _NUMERIC and c.unique > 12]
    if not nums:
        nums = [c.name for c in cols if c.logical_type in _NUMERIC]
    nums.sort(key=lambda n: 0 if any(k in n.lower() for k in _MEASURE_HINTS) else 1)
    cats = [c.name for c in cols if c.logical_type == "text" and 2 <= c.unique <= 30]
    dates = list(loaded.profile.date_columns)
    out: list[str] = []
    if nums and cats:
        out.append(f"What is the total {nums[0]} by {cats[0]}?")
    if nums and dates:
        out.append(f"How did {nums[0]} change by month ({dates[0]})?")
    if nums and len(cats) > 1:
        out.append(f"Which {cats[1]} has the highest {nums[0]}?")
    elif nums and cats:
        out.append(f"Which {cats[0]} has the highest {nums[0]}?")
    return out[:3]


def _on_upload() -> None:
    up = st.session_state.get("upload")
    if up is None:
        return
    dest = session_dir() / safe_name(up.name)
    dest.write_bytes(up.getvalue())
    st.session_state["source"] = {"kind": "upload", "name": up.name, "path": str(dest)}
    st.session_state["sheet"] = None
    st.session_state["preview_key"] = None


def _on_sample() -> None:
    name = st.session_state.get("sample")
    if not name or name == "—":
        return
    for p in sample_files():
        if p.name == name:
            st.session_state["source"] = {"kind": "sample", "name": p.name, "path": str(p)}
            st.session_state["sheet"] = None
            st.session_state["preview_key"] = None


def _use_suggestion(text: str) -> None:
    st.session_state["q"] = text


def _open_preview() -> None:
    st.session_state["preview_key"] = "reviewer-feedback"
    st.session_state["human"] = None
    st.session_state["ws"] = "livewire"


def _clear() -> None:
    st.session_state["source"] = None
    st.session_state["sheet"] = None


def _profile_rows(loaded: Loaded) -> list[list[str]]:
    rows: list[list[str]] = []
    for c in loaded.profile.columns:
        comp = 100 - c.null_pct
        health = (
            '<span class="health ok">✓ Complete</span>'
            if c.nulls == 0
            else f'<span class="health warn">! {c.null_pct:.1f}% missing</span>'
        )
        if c.name in loaded.date_ranges:
            lo, hi = loaded.date_ranges[c.name]
            rng = f"{lo} → {hi}"
        elif c.minimum is not None and c.maximum is not None:
            rng = f"{c.minimum:g} – {c.maximum:g}"
        else:
            rng = ", ".join(c.sample)
        cls = "warn" if c.nulls else ""
        rows.append(
            [
                f"<b>{escape(c.name)}</b>",
                escape(c.logical_type),
                f'<div class="bar"><i class="{cls}" style="width:{comp:.0f}%"></i></div>',
                health,
                f"{c.unique:,}",
                escape(rng),
            ]
        )
    return rows


def render() -> None:
    sheets = sheets_for_current()
    sheet = st.session_state.get("sheet") or (sheets[0] if sheets else None)
    loaded, error = load_current(sheet)
    st.session_state["loaded"] = loaded
    chips = common_chips(loaded) + [h.chip("Idle", "")]
    st.markdown(h.toolbar("Ask & Explore", chips), unsafe_allow_html=True)

    if loaded is not None:
        p, d = loaded.profile, loaded.dataset
        dc = p.date_columns[0] if p.date_columns else None
        miss = sum(c.nulls for c in p.columns)
        n_text = sum(1 for c in p.columns if c.logical_type == "text")
        n_num = sum(1 for c in p.columns if c.logical_type in _NUMERIC)
        rng = loaded.date_ranges.get(dc, ("", "")) if dc else ("", "")
        st.markdown(
            h.strip(
                [
                    (
                        "Rows",
                        f"{p.rows:,}",
                        f"{len(d.sheets) or 1} sheet · {Path(d.name).suffix[1:].upper()}",
                    ),
                    ("Columns", f"{len(p.columns)}", f"{n_text} text · {n_num} numeric"),
                    ("Missing values", f"{miss:,}", "none detected" if not miss else "see profile"),
                    (
                        "Date column",
                        escape(dc) if dc else "—",
                        f"{rng[0]} → {rng[1]}" if dc else "none detected",
                    ),
                    (
                        "Duplicates",
                        f"{p.duplicate_rows:,}",
                        "clean" if not p.duplicate_rows else "review",
                    ),
                ]
            ),
            unsafe_allow_html=True,
        )

    left, mid, right = st.columns([1.05, 3.1, 1.45])
    with left, st.container(key="pane-source"):
        st.markdown(h.pane_header("Data source", step=1), unsafe_allow_html=True)
        st.file_uploader(
            "Upload CSV or XLSX",
            type=["csv", "xlsx"],
            key="upload",
            on_change=_on_upload,
        )
        names = ["—", *[p.name for p in sample_files()]]
        cur = (st.session_state.get("source") or {}).get("name")
        idx = names.index(cur) if cur in names else 0
        st.selectbox(
            "Or use a sample dataset", names, index=idx, key="sample", on_change=_on_sample
        )
        if len(sheets) > 1:
            si = sheets.index(sheet) if sheet in sheets else 0
            st.selectbox("Sheet", sheets, index=si, key="sheet")
        if error:
            st.error(error)
        elif loaded is not None:
            st.markdown(
                '<div class="flag"><span class="ic ok">✓</span><span><b>'
                f"{escape(loaded.dataset.name)}</b> loaded</span></div>"
                '<div class="flag"><span class="ic ok">✓</span><span>Schema readable</span></div>',
                unsafe_allow_html=True,
            )
            st.button("Clear dataset", key="clear", on_click=_clear)
        else:
            st.caption("No dataset yet. Upload a file or pick a sample to begin.")

    with mid, st.container(key="pane-profile"):
        if loaded is None:
            st.markdown(h.pane_header("Profile & preview", step=2), unsafe_allow_html=True)
            st.markdown(
                '<div class="dp-empty"><h3>Start with your data</h3>Upload a CSV or XLSX file, or choose a sample '
                "dataset. DataPilot reads it, checks quality and shows a profile before any question is asked."
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            p, d = loaded.profile, loaded.dataset
            st.markdown(h.pane_header("Profile & preview", d.name, step=2), unsafe_allow_html=True)
            flags = "".join(
                h.chip(f.message, "warn" if f.severity == "warning" else "info") + " "
                for f in p.quality_flags
            ) or h.chip("No quality issues detected", "ok")
            ok_chips = h.chip("Schema readable", "ok")
            st.markdown(
                f'<div class="flush" style="padding:0 var(--pad) var(--pad);display:flex;gap:8px;flex-wrap:wrap">{ok_chips} {flags}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="flush">'
                + h.table(
                    ["Column", "Type", "Completeness", "Quality", "Unique", "Range / samples"],
                    _profile_rows(loaded),
                    right=(4,),
                )
                + "</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                h.pane_header(f"Preview · first 10 of {p.rows:,} rows"), unsafe_allow_html=True
            )
            cols = [c.name for c in p.columns]
            num = {c.name for c in p.columns if c.logical_type in _NUMERIC}
            rows = [[escape(r.get(c, "")) for c in cols] for r in sample_rows(d.frame, 10)]
            st.markdown(
                '<div class="flush">'
                + h.table(cols, rows, right=[i for i, c in enumerate(cols) if c in num])
                + "</div>",
                unsafe_allow_html=True,
            )

    with right, st.container(key="pane-ask"):
        st.markdown(h.pane_header("Ask", step=3), unsafe_allow_html=True)
        st.text_area(
            "Your question",
            key="q",
            height=120,
            placeholder="Ask a question about this dataset…",
            disabled=loaded is None,
        )
        st.segmented_control(
            "Routing",
            ["Guarded selector", "Round-robin"],
            key="mode",
            default="Guarded selector",
            disabled=loaded is None,
        )
        live = get_live()
        blocked = readiness()
        run_clicked = st.button(
            "Run analysis",
            type="primary",
            disabled=loaded is None
            or blocked is not None
            or live.running
            or not (st.session_state.get("q") or "").strip(),
            key="run",
            help=blocked or "Starts a real Planner / Coder / Executor / Reviewer run.",
        )
        if blocked:
            st.caption(blocked)
        if run_clicked and loaded is not None:
            src = st.session_state["source"]
            mode = "round_robin" if st.session_state.get("mode") == "Round-robin" else "selector"
            try:
                live.ask(
                    st.session_state["q"].strip(),
                    path=Path(src["path"]),
                    sheet=st.session_state.get("sheet"),
                    mode=mode,
                )
            except LiveUnavailableError as exc:
                st.error(str(exc))
            else:
                st.session_state["preview_key"] = None
                st.session_state["ws"] = "livewire"
                st.rerun()
        if live.error:
            st.error(f"The last run failed to start: {live.error}")
        if not is_demo():
            st.button("View design preview →", key="to-preview", on_click=_open_preview)
        if loaded is not None:
            st.markdown(
                '<div class="eyebrow" style="margin:14px 0 6px;font-size:11px;text-transform:uppercase;'
                'letter-spacing:.08em;color:var(--muted);font-weight:600">Suggested from this dataset</div>',
                unsafe_allow_html=True,
            )
            for i, text in enumerate(suggestions(loaded)):
                st.button(
                    text,
                    key=f"sugg-{i}",
                    on_click=_use_suggestion,
                    args=(text,),
                    use_container_width=True,
                )
        st.markdown(
            '<div class="eyebrow" style="margin:14px 0 6px;font-size:11px;text-transform:uppercase;'
            'letter-spacing:.08em;color:var(--muted);font-weight:600">Session history</div>',
            unsafe_allow_html=True,
        )
        views = [live.views[r] for r in live.order]
        if not views:
            st.markdown(
                '<div class="muted" style="font-size:12px">No runs yet in this session.</div>',
                unsafe_allow_html=True,
            )
        for v in reversed(views):
            rec = v.record
            st.markdown(
                f'<div class="muted" style="font-size:12px;margin-bottom:4px"><b>r{rec.sequence}</b> · '
                f"{escape(rec.question[:70])} · {rec.outcome.value} · {rec.messages}/12</div>",
                unsafe_allow_html=True,
            )


__all__ = ["IngestionError", "render", "suggestions"]

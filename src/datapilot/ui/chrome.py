"""Shared chrome: theme injection, navigation rail and toolbar chips."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import streamlit as st

from datapilot.agents.usage import PriceTable, UsageTotals
from datapilot.config import get_settings
from datapilot.events import EventType
from datapilot.ui import markup as h
from datapilot.ui.demo import is_demo
from datapilot.ui.preview import events_for
from datapilot.ui.state import Loaded

CSS_PATH = Path(__file__).resolve().parent / "static" / "theme.css"
NAV = (
    ("explore", "Explore", "Ask & Explore", ":material/database:"),
    ("livewire", "Livewire", "Agent Livewire", ":material/hub:"),
    ("insights", "Studio", "Insights Studio", ":material/bar_chart:"),
)


@lru_cache(maxsize=4)
def _css_for(mtime_ns: int) -> str:
    del mtime_ns  # cache key: reload when the stylesheet changes
    return CSS_PATH.read_text(encoding="utf-8")


def _css() -> str:
    return _css_for(CSS_PATH.stat().st_mtime_ns)


def inject_theme() -> None:
    st.markdown(f"<style>{_css()}</style>", unsafe_allow_html=True)


def _go(ws: str) -> None:
    st.session_state["ws"] = ws


def render_rail() -> None:
    """Slim rail on desktop, bottom tab bar on mobile (CSS). Native buttons: no page reload."""
    current = st.session_state.get("ws", "explore")
    with st.container(key="rail"):
        st.markdown('<div class="logo" aria-hidden="true">D</div>', unsafe_allow_html=True)
        for ws, short, full, icon in NAV:
            st.button(
                short,
                key=f"nav-{ws}",
                icon=icon,
                help=full,
                type="primary" if ws == current else "secondary",
                on_click=_go,
                args=(ws,),
            )


def common_chips(loaded: Loaded | None) -> list[str]:
    s = get_settings()
    chips: list[str] = []
    if loaded is not None:
        d = loaded.dataset
        label = f"{d.name} · {len(d.frame):,} rows"
        chips.append(h.chip(label, "info", "hide-m"))
    chips.append(h.chip(s.openai_model, "live", "hide-m"))
    if is_demo():
        chips.append(h.chip("RECORDED RUN · DEMO SITE", "preview"))
    key = st.session_state.get("preview_key")
    if key:  # persistent on every workspace while a scripted preview is active
        chips.append(h.chip("DESIGN PREVIEW", "preview"))
        if any(e.type is EventType.TEST_FAULT_INJECTED for e in events_for(key)):
            chips.append(h.chip("TEST FAULT INJECTED", "test"))
    price = PriceTable.from_settings(s)
    chips.append(
        h.chip(
            price.display(UsageTotals()) if not price.configured else "Pricing configured",
            "warn" if not price.configured else "ok",
            "hide-m",
        )
    )
    return chips

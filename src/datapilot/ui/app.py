"""DataPilot Streamlit entrypoint:  streamlit run src/datapilot/ui/app.py"""

from __future__ import annotations

import logging
import os

import streamlit as st

from datapilot import env_integrity
from datapilot.config import PROJECT_ROOT
from datapilot.logging_setup import configure_logging
from datapilot.ui.chrome import inject_theme, render_rail
from datapilot.ui.state import init_state
from datapilot.ui.workspaces import explore, insights, livewire

WORKSPACES = {"explore": explore.render, "livewire": livewire.render, "insights": insights.render}


log = logging.getLogger(__name__)


@st.cache_resource
def environment_problems() -> tuple[str, ...]:
    """Interpreter/venv/pin drift, checked once per server process (report only, never repairs)."""
    checks = env_integrity.run_checks(PROJECT_ROOT, include_pip=False)
    problems = tuple(f"{c.name}: {c.detail}" for c in checks if not c.ok)
    for problem in problems:
        log.error("environment integrity check failed - %s", problem)
    return problems


def main() -> None:
    st.set_page_config(
        page_title="DataPilot",
        page_icon=":material/hub:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    configure_logging()
    inject_theme()
    init_state()
    render_rail()
    # In the container the image itself is the pinned environment (no project .venv to compare).
    if os.environ.get("DATAPILOT_CONTAINER") != "1" and (problems := environment_problems()):
        st.error("Environment check failed (Python 3.11 venv required): " + "; ".join(problems))
    WORKSPACES[st.session_state["ws"]]()


main()

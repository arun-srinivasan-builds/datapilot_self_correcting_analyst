from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from datapilot import env_integrity
from fixtures import generate

ROOT = Path(__file__).resolve().parents[1]


_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_ES_DISPLAY_REQUIRED = 0x00000002
_keep_awake_active = False


def _set_keep_awake(on: bool) -> bool:
    """Ask Windows not to enter sleep/Modern Standby while the suite runs (process-scoped).

    Root cause of every "unexplained Docker stall" in M3: the laptop entered Modern Standby, which
    freezes the test process and Docker's VM for the whole interval (see
    docs/evidence/m3/stage7-followups-approval.md). Observed: a system-required request alone did
    NOT prevent it; a display-required request is added (the screen stays on during the run). The
    request disappears when the process exits; no system setting is changed. Opt out with
    DATAPILOT_NO_KEEP_AWAKE=1. No-op on other platforms.
    """
    if sys.platform != "win32" or os.environ.get("DATAPILOT_NO_KEEP_AWAKE") == "1":
        return False
    import ctypes

    wanted = _ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED
    flags = _ES_CONTINUOUS | (wanted if on else 0)
    return bool(ctypes.windll.kernel32.SetThreadExecutionState(flags))  # type: ignore[attr-defined]


def pytest_sessionstart(session: pytest.Session) -> None:
    """Fail fast (never silently) when the interpreter or virtualenv is not the pinned 3.11 one."""
    global _keep_awake_active
    failed = [c for c in env_integrity.run_checks(ROOT, include_pip=False) if not c.ok]
    if failed:
        detail = "; ".join(f"{c.name}: {c.detail}" for c in failed)
        pytest.exit(f"Environment integrity check failed - {detail}", returncode=3)
    _keep_awake_active = _set_keep_awake(True)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _keep_awake_active:
        _set_keep_awake(False)


def pytest_report_header(config: pytest.Config) -> str:
    return (
        f"keep-awake (SetThreadExecutionState): {'active' if _keep_awake_active else 'not active'}"
    )


@pytest.fixture(scope="session")
def fx(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Freshly generated fixtures (never the committed copies)."""
    return generate.generate_all(tmp_path_factory.mktemp("fixtures"))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never depend on, or read, real credentials or pricing from the environment."""
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_SEED",
        "MAX_COMPLETION_TOKENS",
        "PRICE_INPUT_PER_1M",
        "PRICE_OUTPUT_PER_1M",
        "MAX_RUN_TOKENS",
        "RUN_TIMEOUT_SECONDS",
        "MAX_AGENT_MESSAGES",
        "APP_ENV",
        "FAULT_INJECTION",
    ):
        monkeypatch.delenv(name, raising=False)

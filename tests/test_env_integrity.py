from __future__ import annotations

import sys
from pathlib import Path

from datapilot import env_integrity as ei

ROOT = Path(__file__).resolve().parents[1]


def by_name(checks):
    return {c.name: c for c in checks}


def test_real_environment_passes_all_checks():
    failed = [c for c in ei.run_checks(ROOT) if not c.ok]
    assert not failed, failed


def test_wrong_interpreter_is_detected(monkeypatch):
    monkeypatch.setattr(sys, "version_info", (3, 14, 0, "final", 0))
    monkeypatch.setattr(sys, "version", "3.14.0 (fake)")
    assert not ei.check_interpreter().ok


def test_repointed_venv_cfg_is_detected(tmp_path, monkeypatch):
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("home = C:\\Python314\nversion = 3.14.0\n", encoding="utf-8")
    monkeypatch.setattr(sys, "prefix", str(venv))
    checks = by_name(ei.check_venv(tmp_path))
    assert checks["venv_is_project_venv"].ok
    assert not checks["pyvenv_cfg_version"].ok


def test_foreign_prefix_is_detected(tmp_path):
    (tmp_path / ".venv").mkdir()
    assert not by_name(ei.check_venv(tmp_path))["venv_is_project_venv"].ok


def test_pin_drift_and_missing_package_are_detected(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "pytest==0.0.1\nnot-a-real-package-xyz==1.0\n", encoding="utf-8"
    )
    (tmp_path / "requirements-dev.txt").write_text("-r requirements.txt\n", encoding="utf-8")
    first = by_name(ei.check_pins(tmp_path))["pins:requirements.txt"]
    assert not first.ok
    assert "pytest" in first.detail and "not installed" in first.detail


def test_missing_requirements_file_fails(tmp_path):
    assert not any(c.ok for c in ei.check_pins(tmp_path))


def test_parse_pins_handles_extras_and_includes(tmp_path):
    path = tmp_path / "req.txt"
    path.write_text("-r other.txt\nautogen-ext[openai]==0.7.5\n# comment\nPyYAML==6.0\n")
    assert ei.parse_pins(path) == {"autogen-ext": "0.7.5", "pyyaml": "6.0"}


def test_legacy_autogen_is_not_installed():
    assert ei.check_forbidden().ok

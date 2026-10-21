"""Interpreter and dependency integrity guard (Python 3.11 is mandatory).

Detects a silently changed interpreter, a re-pointed virtualenv or drifted pins. It only *reports*:
it never recreates or repairs the environment.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

REQUIRED_PYTHON = (3, 11)
FORBIDDEN_DISTRIBUTIONS = ("pyautogen", "autogen", "ag2")
_PIN = re.compile(r"^\s*([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?\s*==\s*([^\s;#]+)")


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    ok: bool
    detail: str


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_pyvenv_cfg(venv: Path) -> dict[str, str]:
    cfg = venv / "pyvenv.cfg"
    values: dict[str, str] = {}
    if cfg.is_file():
        for line in cfg.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep:
                values[key.strip().lower()] = value.strip()
    return values


def parse_pins(requirements: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in requirements.read_text(encoding="utf-8").splitlines():
        match = _PIN.match(line)
        if match:
            pins[_norm(match.group(1))] = match.group(2)
    return pins


def check_interpreter() -> Check:
    ok = tuple(sys.version_info[:2]) == REQUIRED_PYTHON
    return Check("interpreter", ok, f"running {sys.version.split()[0]}, required 3.11.x")


def check_venv(root: Path) -> list[Check]:
    venv = (root / ".venv").resolve()
    in_venv = Path(sys.prefix).resolve() == venv
    cfg = read_pyvenv_cfg(venv)
    version = cfg.get("version") or cfg.get("version_info", "")
    return [
        Check("venv_is_project_venv", in_venv, f"sys.prefix={sys.prefix}, expected {venv}"),
        Check(
            "pyvenv_cfg_version",
            version.startswith("3.11."),
            f"pyvenv.cfg version={version or 'missing'}, home={cfg.get('home', 'missing')}",
        ),
    ]


def _installed_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def check_pins(root: Path) -> list[Check]:
    results: list[Check] = []
    for req in ("requirements.txt", "requirements-dev.txt"):
        path = root / req
        if not path.is_file():
            results.append(Check(f"pins:{req}", False, "file missing"))
            continue
        bad: list[str] = []
        for name, wanted in parse_pins(path).items():
            have = _installed_version(name)
            if have is None:
                bad.append(f"{name} not installed (want {wanted})")
            elif have != wanted:
                bad.append(f"{name} {have} != {wanted}")
        results.append(Check(f"pins:{req}", not bad, "; ".join(bad) or "all pins match"))
    return results


def check_forbidden() -> Check:
    found = [n for n in FORBIDDEN_DISTRIBUTIONS if _installed_version(n) is not None]
    return Check("no_legacy_autogen", not found, f"found: {found}" if found else "none installed")


def check_pip() -> Check:
    proc = subprocess.run(  # noqa: S603 - fixed argv, current interpreter
        [sys.executable, "-m", "pip", "check"], capture_output=True, text=True, timeout=120
    )
    return Check("pip_check", proc.returncode == 0, (proc.stdout + proc.stderr).strip()[:300])


def run_checks(root: Path, *, include_pip: bool = True) -> list[Check]:
    checks = [check_interpreter(), *check_venv(root), *check_pins(root), check_forbidden()]
    if include_pip:
        checks.append(check_pip())
    return checks


def baseline(root: Path) -> dict[str, object]:
    """Facts recorded as evidence of the environment a stage was run in."""
    cfg = root / ".venv" / "pyvenv.cfg"
    pins: dict[str, str] = {}
    for req in ("requirements.txt", "requirements-dev.txt"):
        pins.update(parse_pins(root / req))
    installed = {n: _installed_version(n) for n in sorted(pins)}
    return {
        "python": sys.version,
        "executable": sys.executable,
        "prefix": sys.prefix,
        "pyvenv_cfg_sha256": hashlib.sha256(cfg.read_bytes()).hexdigest()
        if cfg.is_file()
        else None,
        "pyvenv_cfg": read_pyvenv_cfg(root / ".venv"),
        "installed": installed,
    }

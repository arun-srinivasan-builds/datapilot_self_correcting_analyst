"""Environment integrity check. Exit code 1 on any failure. Never repairs anything.

Usage: .venv\\Scripts\\python.exe scripts/check_env.py [--write-baseline PATH]
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datapilot import env_integrity  # noqa: E402


def main(argv: list[str]) -> int:
    checks = env_integrity.run_checks(ROOT)
    report = {
        "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ok": all(c.ok for c in checks),
        "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in checks],
    }
    if "--write-baseline" in argv and report["ok"]:
        target = Path(argv[argv.index("--write-baseline") + 1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({**report, **env_integrity.baseline(ROOT)}, indent=2), encoding="utf-8"
        )
    sys.stdout.write(json.dumps(report, indent=2) + "\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""Fenced Python block extraction, mirroring `CodeExecutorAgent` (python-only, same pattern)."""

from __future__ import annotations

import re

_PYTHON_BLOCK = re.compile(r"```(?:\s*(python))\n([\s\S]*?)```", re.IGNORECASE)


def extract_python_blocks(text: str) -> list[str]:
    return [code for _lang, code in _PYTHON_BLOCK.findall(text)]

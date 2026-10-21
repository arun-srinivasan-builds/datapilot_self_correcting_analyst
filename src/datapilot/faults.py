"""Controlled, TEST-ONLY fault injection (PRP §8, "Demo B").

A fault deterministically mutates the Coder's code message *before it enters the conversation*, so
the faulty code is what the Executor really runs, what the Reviewer sees, and what the Coder's own
memory says it wrote (see `FaultInjectingCoder`). Nothing is faked downstream: the resulting
error is a genuine Python exception raised in a real sandbox container.

Guardrails
- Off by default. A `FaultInjector` can only be created through `authorize()`, which refuses
  unless the process is explicitly in test/diagnostic mode (`APP_ENV=test|diagnostic`) AND
  `FAULT_INJECTION` names exactly that fault. Production code paths (the UI and
  `RunConfig.from_settings`) never create one.
- A fault that does not apply to the code (pattern absent) raises instead of silently doing nothing.
- Every injection emits a `test_fault_injected` event first and records original code, mutated code,
  hashes and identifiers. Executions of injected code carry `injected_fault` in their events.
- No messages, tool calls or results are added, so the 12-message, token, timeout and approval rules
  apply unchanged.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

from datapilot.config import Settings
from datapilot.events import EventStore, EventType

log = logging.getLogger(__name__)
FAULT_SOURCE = "test_harness"
ALLOWED_MODES = ("test", "diagnostic")
MAX_INJECTIONS = 8
_TOKEN = object()  # only `authorize()` holds this; constructing an injector otherwise is refused


class FaultInjectionRefused(RuntimeError):
    """Fault injection was requested outside the explicit test/diagnostic boundary."""


class FaultInjectionError(RuntimeError):
    """The fault could not be applied faithfully (never fall back to a silent no-op)."""


@dataclass(frozen=True, slots=True)
class FaultSpec:
    name: str
    description: str
    find: str
    replace: str

    def apply(self, code: str) -> str:
        if self.find not in code:
            raise FaultInjectionError(f"fault '{self.name}' does not apply: pattern not in code")
        mutated = code.replace(self.find, self.replace, 1)
        if mutated == code:  # pragma: no cover - find == replace
            raise FaultInjectionError(f"fault '{self.name}' did not change the code")
        return mutated


FAULTS: dict[str, FaultSpec] = {
    "missing_column": FaultSpec(
        "missing_column",
        "Coder's code mutated: column reference 'units' renamed to 'qty' (raises KeyError)",
        'df["units"]',
        'df["qty"]',
    ),
    "bad_column_lookup": FaultSpec(
        "bad_column_lookup",
        "Coder's code mutated: a lookup of a non-existent column 'qty' inserted right after the "
        "pandas import (raises a genuine KeyError in the sandbox)",
        "import pandas as pd",
        "import pandas as pd\n"
        "_qty_check = pd.read_csv(__import__('os').environ['DATA_PATH'])['qty']  # TEST FAULT",
    ),
    "hang": FaultSpec(
        "hang",
        "Coder's code mutated: an endless loop inserted after the imports (never terminates)",
        "import json, os",
        "import json, os\nwhile True:\n    pass",
    ),
}


def authorize(settings: Settings, name: str) -> FaultSpec:
    """The only door to fault injection. Refuses unless test/diagnostic mode names this fault."""
    if settings.app_env not in ALLOWED_MODES:
        raise FaultInjectionRefused(
            f"fault injection needs APP_ENV in {ALLOWED_MODES} (got {settings.app_env!r})"
        )
    if settings.fault_injection != name:
        raise FaultInjectionRefused("FAULT_INJECTION does not name this fault; refusing")
    if name not in FAULTS:
        raise FaultInjectionRefused(f"unknown fault '{name}'")
    return FAULTS[name]


def code_digest(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True, slots=True)
class FaultRecord:
    """Everything needed to audit one injection."""

    fault: str
    occurrence: int
    original_content: str
    mutated_content: str
    original_code: str
    mutated_code: str
    original_hash: str
    mutated_hash: str

    @property
    def diff(self) -> str:
        return "\n".join(
            difflib.unified_diff(
                self.original_code.splitlines(),
                self.mutated_code.splitlines(),
                "original (Coder's own output)",
                "executed (after test-only mutation)",
                lineterm="",
            )
        )


@dataclass
class FaultInjector:
    """Mutates the first `times` valid Coder code messages of one run."""

    spec: FaultSpec
    times: int = 1
    _token: object = field(default=None, repr=False)
    records: list[FaultRecord] = field(default_factory=list)
    _store: EventStore | None = field(default=None, repr=False)
    _injected_hashes: dict[str, str] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self._token is not _TOKEN:
            raise FaultInjectionRefused("create fault injectors with FaultInjector.authorized()")
        if not 1 <= self.times <= MAX_INJECTIONS:
            raise FaultInjectionRefused(f"times must be 1..{MAX_INJECTIONS}")

    @classmethod
    def authorized(cls, settings: Settings, name: str, *, times: int = 1) -> FaultInjector:
        return cls(authorize(settings, name), times, _token=_TOKEN)

    def attach(self, store: EventStore, injected_hashes: dict[str, str]) -> None:
        self._store, self._injected_hashes = store, injected_hashes

    @property
    def remaining(self) -> int:
        return self.times - len(self.records)

    def inject(self, content: str, original_code: str) -> tuple[str, FaultRecord]:
        """Return the mutated message content and its record (event emitted first)."""
        if self._store is None or self._injected_hashes is None:
            raise FaultInjectionError("injector is not attached to a run; refusing to mutate")
        mutated_code = self.spec.apply(original_code)
        mutated_content = content.replace(original_code, mutated_code, 1)
        record = FaultRecord(
            self.spec.name,
            len(self.records) + 1,
            content,
            mutated_content,
            original_code,
            mutated_code,
            code_digest(original_code),
            code_digest(mutated_code),
        )
        self._injected_hashes[record.mutated_hash] = self.spec.name
        self._store.append(
            EventType.TEST_FAULT_INJECTED,
            FAULT_SOURCE,
            {
                "fault": self.spec.name,
                "detail": self.spec.description,
                "occurrence": record.occurrence,
                "original_hash": record.original_hash,
                "mutated_hash": record.mutated_hash,
                "test_only": True,
            },
        )
        self.records.append(record)
        log.warning("TEST FAULT INJECTED: %s (occurrence %d)", self.spec.name, record.occurrence)
        return mutated_content, record

    def summary(self) -> dict[str, Any]:
        return {
            "fault": self.spec.name,
            "description": self.spec.description,
            "injections": [
                {
                    "occurrence": r.occurrence,
                    "original_hash": r.original_hash,
                    "mutated_hash": r.mutated_hash,
                    "diff": r.diff,
                }
                for r in self.records
            ],
        }

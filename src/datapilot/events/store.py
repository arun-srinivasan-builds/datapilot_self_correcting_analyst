"""Thread-safe, append-only event store. Worker thread appends; UI thread polls `since`."""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from datapilot.events.models import EventType, RuntimeEvent


class EventStore:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._events: list[RuntimeEvent] = []
        self._lock = threading.Lock()

    def append(
        self, type_: EventType, source: str, payload: Mapping[str, Any] | None = None
    ) -> RuntimeEvent:
        """Record one real occurrence. `seq` is assigned here, starting at 1, gap-free."""
        with self._lock:
            event = RuntimeEvent(
                seq=len(self._events) + 1,
                run_id=self.run_id,
                ts=datetime.now(UTC),
                type=type_,
                source=source,
                payload=payload or {},
            )
            self._events.append(event)
            return event

    def snapshot(self) -> tuple[RuntimeEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def since(self, after_seq: int = 0) -> tuple[RuntimeEvent, ...]:
        with self._lock:
            return tuple(self._events[after_seq:])

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)

    def dump_jsonl(self, path: Path) -> None:
        lines = [json.dumps(e.to_dict(), ensure_ascii=False) for e in self.snapshot()]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

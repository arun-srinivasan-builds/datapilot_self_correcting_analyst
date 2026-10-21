"""Structured JSON logging with secret redaction."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

_SECRET = re.compile(r"sk-[A-Za-z0-9_\-*.]{6,}")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": _SECRET.sub("[REDACTED]", record.getMessage()),
        }
        if record.exc_info:
            payload["exc"] = _SECRET.sub("[REDACTED]", self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())

    # AutoGen's INFO events carry full prompts (dataset samples included) and model replies: keep
    # them out of application logs. Warnings and errors still come through.
    for noisy in ("autogen_core", "autogen_core.events", "autogen_agentchat", "httpx", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

"""Broker configuration. Standard library only; the broker never imports the application."""

from __future__ import annotations

import ipaddress
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

MB = 1024 * 1024
MIN_TOKEN_LENGTH = 24
LOOPBACK_HOSTS = ("127.0.0.1", "::1")
_DEFAULT_LOCK = Path(__file__).resolve().parents[1] / "image" / "image.lock.json"


class ConfigError(ValueError):
    """The broker refuses to start with this configuration."""


@dataclass(frozen=True, slots=True)
class BrokerConfig:
    token: str
    root: Path
    lock_path: Path = _DEFAULT_LOCK
    host: str = "127.0.0.1"
    port: int = 8765
    max_dataset_bytes: int = 25 * MB
    max_json_bytes: int = 512 * 1024
    max_code_bytes: int = 200_000
    default_timeout_s: int = 60
    max_timeout_s: int = 120
    max_concurrent: int = 2
    memory: str = "512m"
    cpus: str = "1.0"
    pids: int = 128
    output_cap_bytes: int = 256 * 1024
    max_artifacts: int = 20
    max_artifact_bytes: int = 5 * MB
    max_out_total_bytes: int = 64 * MB
    artifact_ttl_s: int = 3600
    dataset_ttl_s: int = 6 * 3600
    container_prefix: str = "dpsbx-"

    def validate(self) -> None:
        if len(self.token) < MIN_TOKEN_LENGTH:
            raise ConfigError(f"SANDBOX_TOKEN must be at least {MIN_TOKEN_LENGTH} characters")
        if self.host not in LOOPBACK_HOSTS:
            raise ConfigError(f"broker binds loopback only ({LOOPBACK_HOSTS}), got {self.host!r}")
        ipaddress.ip_address(self.host)
        if not 0 <= self.port <= 65535:  # 0 = ephemeral (tests)
            raise ConfigError("port out of range")
        if any(ch in str(self.root) for ch in ",\"'\n"):
            raise ConfigError("SANDBOX_ROOT must not contain commas or quotes")
        if self.max_timeout_s < self.default_timeout_s or self.default_timeout_s < 1:
            raise ConfigError("invalid timeout configuration")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> BrokerConfig:
        env = os.environ if env is None else env
        cfg = cls(
            token=env.get("SANDBOX_TOKEN", ""),
            root=Path(env.get("SANDBOX_ROOT", ".sandbox")).resolve(),
            host=env.get("SANDBOX_BIND_HOST", "127.0.0.1"),
            port=int(env.get("SANDBOX_PORT", "8765")),
            default_timeout_s=int(env.get("SANDBOX_TIMEOUT_SECONDS", "60")),
            max_dataset_bytes=int(env.get("MAX_UPLOAD_MB", "25")) * MB,
        )
        cfg.validate()
        return cfg


@dataclass(frozen=True, slots=True)
class ImageLock:
    image_id: str
    raw: Mapping[str, object]

    @classmethod
    def load(cls, path: Path) -> ImageLock:
        data = json.loads(path.read_text(encoding="utf-8"))
        image_id = str(data.get("image_id", ""))
        if not image_id.startswith("sha256:") or len(image_id) != 71:
            raise ConfigError("image.lock.json has no valid image_id")
        return cls(image_id, data)

"""Environment-only application settings. Values come from the process env or a local `.env`."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLACEHOLDER_KEY = "YOUR_OPENAI_API_KEY_HERE"


class Settings(BaseSettings):
    """Typed settings. The API key is a SecretStr so it never appears in repr/logs."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-6-luna"
    max_agent_messages: int = 12
    sandbox_url: str = "http://127.0.0.1:8765"
    sandbox_timeout_seconds: int = 60
    sandbox_token: SecretStr = SecretStr("")
    max_upload_mb: int = 25
    log_level: str = "INFO"
    max_rows: int = 1_000_000
    max_columns: int = 200
    # Live-run safety limits (independent of the 12-agent-message cap).
    app_env: str = "production"  # production | test | diagnostic
    fault_injection: str = ""  # names a fault; honoured ONLY when app_env is test/diagnostic
    max_run_tokens: int = Field(default=30_000, ge=1)
    run_timeout_seconds: int = Field(default=300, ge=1)
    openai_seed: int | None = None
    max_completion_tokens: int | None = None
    # Pricing is user-supplied (USD per 1M tokens). No default: unset => "Pricing not configured".
    price_input_per_1m: float | None = None
    price_output_per_1m: float | None = None

    @field_validator(
        "openai_seed",
        "max_completion_tokens",
        "price_input_per_1m",
        "price_output_per_1m",
        mode="before",
    )
    @classmethod
    def _blank_is_none(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("app_env")
    @classmethod
    def _known_env(cls, value: str) -> str:
        if value not in ("production", "test", "diagnostic"):
            raise ValueError("APP_ENV must be production, test or diagnostic")
        return value

    @property
    def pricing_configured(self) -> bool:
        return self.price_input_per_1m is not None and self.price_output_per_1m is not None

    @property
    def has_api_key(self) -> bool:
        value = self.openai_api_key.get_secret_value().strip()
        return bool(value) and value != PLACEHOLDER_KEY


@lru_cache
def get_settings() -> Settings:
    return Settings()

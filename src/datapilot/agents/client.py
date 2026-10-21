"""Model client factory for gpt-6-luna.

Verified in M2 step 0 (docs/evidence/m2/model-check.md): `max_tokens` and `temperature != 1` are
rejected, `seed` is accepted, and AutoGen needs an explicit `model_info`. We therefore never send
`temperature`/`max_tokens`. function_calling/structured_output/json_output are declared False
until proven (decision C5).
"""

from __future__ import annotations

from typing import Any

from autogen_core.models import ModelInfo
from autogen_ext.models.openai import OpenAIChatCompletionClient

from datapilot.config import Settings

MODEL_INFO: ModelInfo = {
    "vision": False,
    # C5 (approved 2026-10-16): capabilities not proven for gpt-6-luna are declared False. M3 uses
    # no tools and no structured output. Flip only after a verified live probe.
    "function_calling": False,
    "json_output": False,
    "family": "unknown",
    "structured_output": False,
}


def client_kwargs(settings: Settings) -> dict[str, Any]:
    """Keyword arguments for the AutoGen client. Contains no unsupported parameter."""
    kwargs: dict[str, Any] = {
        "model": settings.openai_model,
        "api_key": settings.openai_api_key.get_secret_value(),
        "model_info": MODEL_INFO,
    }
    if settings.openai_seed is not None:
        kwargs["seed"] = settings.openai_seed
    if settings.max_completion_tokens is not None:
        kwargs["max_completion_tokens"] = settings.max_completion_tokens
    return kwargs


def build_model_client(settings: Settings) -> OpenAIChatCompletionClient:
    if not settings.has_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured; refusing to build a model client.")
    return OpenAIChatCompletionClient(**client_kwargs(settings))

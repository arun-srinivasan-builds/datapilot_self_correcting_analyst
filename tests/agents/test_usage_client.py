from __future__ import annotations

from types import SimpleNamespace

import pytest

from datapilot.agents.client import MODEL_INFO, build_model_client, client_kwargs
from datapilot.agents.usage import PRICING_NOT_CONFIGURED, PriceTable, UsageTotals, UsageTracker
from datapilot.config import PLACEHOLDER_KEY, Settings

KEY = "sk-test-123456"


def settings(**env) -> Settings:
    return Settings(_env_file=None, **env)


def test_tracker_sums_real_usage_and_ignores_missing():
    t = UsageTracker()
    t.record("Planner", SimpleNamespace(prompt_tokens=100, completion_tokens=40))
    t.record("Coder", SimpleNamespace(prompt_tokens=300, completion_tokens=200))
    t.record("Coder", SimpleNamespace(prompt_tokens=50, completion_tokens=10))
    t.record("Executor", None)
    assert t.total() == UsageTotals(450, 250, 3)
    assert t.by_source()["Coder"].total_tokens == 560
    assert "Executor" not in t.by_source()


def test_pricing_not_configured_is_explicit():
    totals = UsageTotals(1000, 500, 2)
    table = PriceTable.from_settings(settings())
    assert not table.configured and table.cost(totals) is None
    assert table.display(totals) == PRICING_NOT_CONFIGURED
    half = PriceTable(input_per_1m=1.0, output_per_1m=None)
    assert half.display(totals) == PRICING_NOT_CONFIGURED


def test_configured_pricing_math():
    table = PriceTable(2.0, 8.0)
    assert table.cost(UsageTotals(1_000_000, 500_000, 1)) == pytest.approx(6.0)
    assert table.display(UsageTotals(1_000_000, 500_000, 1)) == "$6.0000"


def test_blank_env_values_mean_unset():
    s = settings(price_input_per_1m="", openai_seed="", max_completion_tokens=" ")
    assert s.price_input_per_1m is None and s.openai_seed is None
    assert s.max_completion_tokens is None


def test_placeholder_key_is_not_a_key():
    assert not settings(openai_api_key=PLACEHOLDER_KEY).has_api_key
    assert not settings().has_api_key
    assert settings(openai_api_key=KEY).has_api_key


def test_secret_never_in_repr():
    s = settings(openai_api_key=KEY)
    assert KEY not in repr(s) and KEY not in str(s)


def test_client_kwargs_exclude_unsupported_params():
    kw = client_kwargs(settings(openai_api_key=KEY))
    assert kw["model_info"] == MODEL_INFO
    assert "temperature" not in kw and "max_tokens" not in kw
    kw2 = client_kwargs(settings(openai_api_key=KEY, openai_seed=7, max_completion_tokens=900))
    assert kw2["seed"] == 7 and kw2["max_completion_tokens"] == 900


def test_autogen_maps_max_completion_tokens_offline():
    """Offline: constructing the client sends nothing. Confirms AutoGen keeps the parameter."""
    c = build_model_client(settings(openai_api_key=KEY, max_completion_tokens=900, openai_seed=3))
    args = c._create_args  # noqa: SLF001 - verifying library parameter mapping
    assert args["max_completion_tokens"] == 900 and args["seed"] == 3
    assert "max_tokens" not in args and "temperature" not in args
    assert args["model"] == "gpt-6-luna"


def test_no_client_without_key():
    with pytest.raises(RuntimeError):
        build_model_client(settings())


def test_unproven_capabilities_are_declared_false():
    assert not MODEL_INFO["function_calling"]
    assert not MODEL_INFO["structured_output"]
    assert not MODEL_INFO["json_output"]
    assert not MODEL_INFO["vision"]

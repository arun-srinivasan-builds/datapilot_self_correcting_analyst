"""Token usage accounting from AutoGen `models_usage` (RequestUsage). Prices are user-supplied."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol

from datapilot.config import Settings

PRICING_NOT_CONFIGURED = "Pricing not configured"


class _Usage(Protocol):
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True, slots=True)
class UsageTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class PriceTable:
    input_per_1m: float | None = None
    output_per_1m: float | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> PriceTable:
        return cls(settings.price_input_per_1m, settings.price_output_per_1m)

    @property
    def configured(self) -> bool:
        return self.input_per_1m is not None and self.output_per_1m is not None

    def cost(self, totals: UsageTotals) -> float | None:
        if self.input_per_1m is None or self.output_per_1m is None:
            return None
        return (
            totals.input_tokens * self.input_per_1m + totals.output_tokens * self.output_per_1m
        ) / 1_000_000

    def display(self, totals: UsageTotals) -> str:
        cost = self.cost(totals)
        return PRICING_NOT_CONFIGURED if cost is None else f"${cost:,.4f}"


class UsageTracker:
    """Accumulates real usage reported by the model client, per agent. No estimation."""

    def __init__(self) -> None:
        self._by_source: dict[str, UsageTotals] = defaultdict(UsageTotals)

    def record(self, source: str, usage: _Usage | None) -> None:
        """Record one message's `models_usage`; messages without usage (executor) are ignored."""
        if usage is None:
            return
        prev = self._by_source[source]
        self._by_source[source] = UsageTotals(
            prev.input_tokens + usage.prompt_tokens,
            prev.output_tokens + usage.completion_tokens,
            prev.calls + 1,
        )

    def by_source(self) -> dict[str, UsageTotals]:
        return dict(self._by_source)

    def total(self) -> UsageTotals:
        return UsageTotals(
            sum(t.input_tokens for t in self._by_source.values()),
            sum(t.output_tokens for t in self._by_source.values()),
            sum(t.calls for t in self._by_source.values()),
        )

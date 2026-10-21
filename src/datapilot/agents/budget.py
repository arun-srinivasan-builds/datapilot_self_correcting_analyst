"""Run-level token budget enforcement around every model call (agents and selector fallback).

Accounting: usage reported by the model for each call is added to `RunState` right after the call
(so selector-fallback calls count too). Enforcement: before each call, a call is refused if the
already-used tokens plus the locally estimated prompt tokens would exceed `max_tokens`.

Limitations (reported, not hidden):
- Without a configured per-call ceiling (`MAX_COMPLETION_TOKENS`, sent as `max_completion_tokens`)
  one completion can overshoot the budget; the next call is then refused. With a ceiling, it is
  reserved before each call, so overshoot is bounded by the estimator error only.
- Prompt estimation uses the client's own tokenizer approximation, not the model's exact count.
- Whether `completion_tokens` includes hidden reasoning tokens depends on the model API and has not
  been verified (no live call yet); we count exactly what the API reports.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping, Sequence
from typing import Any, Literal

from autogen_core import CancellationToken
from autogen_core.models import (
    ChatCompletionClient,
    CreateResult,
    LLMMessage,
    ModelCapabilities,  # type: ignore[attr-defined]
    ModelInfo,
    RequestUsage,
)
from autogen_core.tools import Tool, ToolSchema
from pydantic import BaseModel

from datapilot.agents.termination import RunState
from datapilot.events import EventStore, EventType


class TokenBudgetExhaustedError(RuntimeError):
    """Raised instead of making a model call that would exceed the run's token budget."""


class BudgetedClient(ChatCompletionClient):
    def __init__(
        self,
        inner: ChatCompletionClient,
        state: RunState,
        source: str,
        store: EventStore | None = None,
        ceiling: int | None = None,
    ) -> None:
        self._inner = inner
        self._state = state
        self._source = source
        self._store = store
        self._ceiling = ceiling  # per-call completion ceiling already configured on the client

    def _record(self, usage: RequestUsage) -> None:
        self._state.add_usage(usage.prompt_tokens, usage.completion_tokens, self._source)
        if self._store is not None:  # one event per real model call, selector calls included
            self._store.append(
                EventType.USAGE,
                self._source,
                {"input_tokens": usage.prompt_tokens, "output_tokens": usage.completion_tokens},
            )

    def _guard(self, messages: Sequence[LLMMessage], tools: Sequence[Tool | ToolSchema]) -> None:
        state = self._state
        try:
            estimate = self._inner.count_tokens(messages, tools=tools)
        except Exception:  # an estimator failure must not disable the budget check below
            estimate = 0
        reserved = self._ceiling or 0  # with a ceiling a single call cannot overshoot the budget
        if state.total_tokens + estimate + reserved >= state.max_tokens:
            state.block_for_budget(estimate)
            raise TokenBudgetExhaustedError(
                f"token budget {state.max_tokens} exhausted "
                f"(used {state.total_tokens}, next prompt ~{estimate})"
            )

    async def create(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[Tool | ToolSchema] = [],
        tool_choice: Tool | Literal["auto", "required", "none"] = "auto",
        json_output: bool | type[BaseModel] | None = None,
        extra_create_args: Mapping[str, Any] = {},
        cancellation_token: CancellationToken | None = None,
    ) -> CreateResult:
        self._guard(messages, tools)
        result = await self._inner.create(
            messages,
            tools=tools,
            tool_choice=tool_choice,
            json_output=json_output,
            extra_create_args=extra_create_args,
            cancellation_token=cancellation_token,
        )
        self._record(result.usage)
        return result

    async def create_stream(  # type: ignore[override]
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[Tool | ToolSchema] = [],
        tool_choice: Tool | Literal["auto", "required", "none"] = "auto",
        json_output: bool | type[BaseModel] | None = None,
        extra_create_args: Mapping[str, Any] = {},
        cancellation_token: CancellationToken | None = None,
    ) -> AsyncGenerator[str | CreateResult, None]:
        self._guard(messages, tools)
        async for item in self._inner.create_stream(
            messages,
            tools=tools,
            tool_choice=tool_choice,
            json_output=json_output,
            extra_create_args=extra_create_args,
            cancellation_token=cancellation_token,
        ):
            if isinstance(item, CreateResult):
                self._record(item.usage)
            yield item

    async def close(self) -> None:
        await self._inner.close()

    def actual_usage(self) -> RequestUsage:
        return self._inner.actual_usage()

    def total_usage(self) -> RequestUsage:
        return self._inner.total_usage()

    def count_tokens(
        self, messages: Sequence[LLMMessage], *, tools: Sequence[Tool | ToolSchema] = []
    ) -> int:
        return self._inner.count_tokens(messages, tools=tools)

    def remaining_tokens(
        self, messages: Sequence[LLMMessage], *, tools: Sequence[Tool | ToolSchema] = []
    ) -> int:
        return self._inner.remaining_tokens(messages, tools=tools)

    @property
    def capabilities(self) -> ModelCapabilities:  # type: ignore[override]
        return self._inner.capabilities  # type: ignore[return-value]

    @property
    def model_info(self) -> ModelInfo:
        return self._inner.model_info

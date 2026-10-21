"""The four autonomous participants (modern AgentChat API). User Proxy is a separate human stage."""

from __future__ import annotations

import warnings
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass
from typing import Any

from autogen_agentchat.agents import AssistantAgent, CodeExecutorAgent
from autogen_agentchat.base import Response
from autogen_agentchat.messages import BaseChatMessage, TextMessage
from autogen_core import CancellationToken
from autogen_core.code_executor import CodeBlock, CodeExecutor
from autogen_core.models import AssistantMessage, ChatCompletionClient

from datapilot.agents import prompts
from datapilot.agents.codeblocks import extract_python_blocks
from datapilot.faults import FaultInjectionError, FaultInjector

CODER = "Coder"


class FaultInjectingCoder(AssistantAgent):
    """TEST-ONLY Coder whose first code message(s) are mutated by an authorized `FaultInjector`.

    The mutated text replaces the Response (so every other agent and the Executor see it) AND the
    assistant message AutoGen already stored in this agent's own model context, so the Coder's
    memory describes exactly the code that is executed. If the memory cannot be reconciled the run
    is refused (FaultInjectionError); the mismatch is never hidden.
    """

    def __init__(self, *args: Any, injector: FaultInjector, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._injector = injector

    async def on_messages_stream(
        self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken
    ) -> AsyncGenerator[Any, None]:
        async for item in super().on_messages_stream(messages, cancellation_token):
            if isinstance(item, Response) and self._injector.remaining > 0:
                item = await self._mutate(item)
            yield item

    async def _mutate(self, response: Response) -> Response:
        message = response.chat_message
        blocks = extract_python_blocks(message.content) if isinstance(message, TextMessage) else []
        if len(blocks) != 1:
            return response  # only a usable, single-block code message is a fault target
        mutated_content, _record = self._injector.inject(message.content, blocks[0])
        context = self._model_context
        history = list(await context.get_messages())  # a copy: contexts may return their list
        last = history[-1] if history else None
        if not isinstance(last, AssistantMessage) or last.content != message.content:
            raise FaultInjectionError("cannot reconcile the Coder's memory with the injected code")
        await context.clear()
        for earlier in history[:-1]:
            await context.add_message(earlier)
        await context.add_message(
            AssistantMessage(content=mutated_content, source=last.source, thought=last.thought)
        )
        rewritten = await context.get_messages()  # verify, never assume
        if len(rewritten) != len(history) or rewritten[-1].content != mutated_content:
            raise FaultInjectionError("Coder memory does not match the injected code after rewrite")
        return Response(
            chat_message=TextMessage(
                content=mutated_content, source=message.source, models_usage=message.models_usage
            ),
            inner_messages=response.inner_messages,
        )


class LatestCoderExecutorAgent(CodeExecutorAgent):
    """Executes only the code in the Coder's LATEST message.

    The stock agent concatenates every python block of every Coder message buffered since its last
    turn. After an unusable Coder reply (no block, several blocks) the stale blocks would be bundled
    with the next valid script and the whole run rejected. Found by the Stage 5 integration tests.
    """

    async def extract_code_blocks_from_messages(
        self, messages: Sequence[BaseChatMessage]
    ) -> list[CodeBlock]:
        for message in reversed(messages):
            if message.source == CODER and isinstance(message, TextMessage):
                return self._extract_markdown_code_blocks(message.content)
        return []


@dataclass(frozen=True, slots=True)
class RoleClients:
    """One model client per LLM role (per-role usage attribution; production may share one)."""

    planner: ChatCompletionClient
    coder: ChatCompletionClient
    reviewer: ChatCompletionClient

    @classmethod
    def shared(cls, client: ChatCompletionClient) -> RoleClients:
        return cls(client, client, client)


@dataclass(frozen=True, slots=True)
class Participants:
    planner: AssistantAgent
    coder: AssistantAgent
    executor: CodeExecutorAgent
    reviewer: AssistantAgent

    def in_cycle_order(self) -> list[AssistantAgent | CodeExecutorAgent]:
        """Planner -> Coder -> Executor -> Reviewer (the RoundRobin baseline order)."""
        return [self.planner, self.coder, self.executor, self.reviewer]


def build_participants(
    clients: RoleClients,
    code_executor: CodeExecutor,
    fault_injector: FaultInjector | None = None,
) -> Participants:
    planner = AssistantAgent(
        "Planner",
        clients.planner,
        system_message=prompts.PLANNER_PROMPT,
        description=prompts.PLANNER_DESCRIPTION,
    )
    coder_args: dict[str, Any] = {
        "system_message": prompts.CODER_PROMPT,
        "description": prompts.CODER_DESCRIPTION,
    }
    coder: AssistantAgent = (
        FaultInjectingCoder("Coder", clients.coder, injector=fault_injector, **coder_args)
        if fault_injector is not None
        else AssistantAgent("Coder", clients.coder, **coder_args)
    )
    reviewer = AssistantAgent(
        "Reviewer",
        clients.reviewer,
        system_message=prompts.REVIEWER_PROMPT,
        description=prompts.REVIEWER_DESCRIPTION,
    )
    with warnings.catch_warnings():
        # The library warns that no approval_func is set. Execution is confined to the sandbox
        # service by construction (ObservedCodeExecutor -> ExecutionBackend), and human approval
        # of code before execution is not part of the autonomous loop.
        warnings.filterwarnings("ignore", message="No approval function set")
        executor = LatestCoderExecutorAgent(
            "Executor",
            code_executor=code_executor,
            sources=[CODER],
            supported_languages=["python"],
            description=prompts.EXECUTOR_DESCRIPTION,
        )
    return Participants(planner, coder, executor, reviewer)

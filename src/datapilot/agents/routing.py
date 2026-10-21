"""Guarded speaker selection (PRP §3.1). Error routing is never left to the LLM.

| last agent message                         | next                                   |
|--------------------------------------------|----------------------------------------|
| (none: only the task)                      | Planner                                |
| Planner                                    | Coder                                  |
| Coder with exactly one python block        | Executor                               |
| Coder without / with several blocks        | Coder (deterministic; GUARDRAIL event) |
| Executor, execution failed or not executed | Coder (+ REPAIR_ROUTED)                |
| Executor, execution ok                     | Reviewer                               |
| Reviewer (not approved)                    | Coder                                  |

Anything else returns `None`, which lets the selector LLM choose (defensive; not expected).
"""

from __future__ import annotations

from collections.abc import Sequence

from autogen_agentchat.messages import BaseAgentEvent, BaseChatMessage

from datapilot.agents.codeblocks import extract_python_blocks
from datapilot.agents.termination import RunState, message_text
from datapilot.events import EventStore, EventType
from datapilot.events.models import AGENTS

SELECTOR_SOURCE = "selector"


class GuardedSelector:
    def __init__(self, state: RunState, store: EventStore | None = None) -> None:
        self._state = state
        self._store = store
        self.repairs = 0

    def __call__(self, messages: Sequence[BaseAgentEvent | BaseChatMessage]) -> str | None:
        last = self._last_agent_message(messages)
        if last is None:
            return self._select("Planner", "start")
        verdict = self._state.observe(last.id, last.source, message_text(last), last.models_usage)
        source = last.source
        if source == "Planner":
            return self._select("Coder", "plan_done")
        if source == "Coder":
            if len(extract_python_blocks(message_text(last))) == 1:
                return self._select("Executor", "code_ready")
            return self._select("Coder", "invalid_code_block")
        if source == "Executor":
            if self._state.last_exec_ok:
                return self._select("Reviewer", "exec_ok")
            self.repairs += 1
            self._emit(EventType.REPAIR_ROUTED, {"attempt": self.repairs})
            return self._select("Coder", "exec_failed")
        if source == "Reviewer" and not verdict.approved:
            return self._select("Coder", "review_feedback")
        return None

    @staticmethod
    def _last_agent_message(
        messages: Sequence[BaseAgentEvent | BaseChatMessage],
    ) -> BaseChatMessage | None:
        for message in reversed(messages):
            if isinstance(message, BaseChatMessage) and message.source in AGENTS:
                return message
        return None

    def _select(self, name: str, rule: str) -> str:
        self._emit(EventType.SPEAKER_SELECTED, {"next": name, "rule": rule})
        return name

    def _emit(self, type_: EventType, payload: dict[str, object]) -> None:
        if self._store is not None:
            self._store.append(type_, SELECTOR_SOURCE, payload)

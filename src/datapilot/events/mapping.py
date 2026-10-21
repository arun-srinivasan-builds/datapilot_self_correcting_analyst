"""AutoGen messages -> normalized `RuntimeEvent`s. Every event has a real source; none are invented.

Chat messages are mapped from inside the team (via `RunTerminator`), which runs for each message
before the next speaker is selected, so event order equals the order the team actually processed.
Execution events come from `ObservedCodeExecutor`, speaker/repair events from `GuardedSelector`;
the stream consumer only contributes the final `TaskResult`.
"""

from __future__ import annotations

import re

from autogen_agentchat.base import TaskResult
from autogen_agentchat.messages import BaseChatMessage

from datapilot.agents.codeblocks import extract_python_blocks
from datapilot.agents.executor import code_hash
from datapilot.agents.termination import MessageVerdict, RunOutcome, RunState, message_text
from datapilot.events import EventStore, EventType
from datapilot.events.models import AGENTS

_NUMBERED = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
_LIMIT_KIND = {
    RunOutcome.LIMIT_REACHED: "messages",
    RunOutcome.TOKEN_BUDGET_EXHAUSTED: "tokens",
    RunOutcome.TIMEOUT: "time",
    RunOutcome.STOPPED: "stopped",
}


def _first_line(text: str, limit: int = 120) -> str:
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return line if len(line) <= limit else line[: limit - 1] + "…"


class EventMapper:
    def __init__(self, store: EventStore, state: RunState, mode: str) -> None:
        self._store = store
        self._state = state
        self._mode = mode
        self._mapped: set[str] = set()
        self._code_versions = 0
        self._terminal_emitted = False

    def _injected_flag(self, digest: str) -> dict[str, str]:
        fault = self._state.injected_hashes.get(digest)
        return {"injected_fault": fault} if fault else {}

    # -- speaker announcements -------------------------------------------------------------
    def announce_first_speaker(self) -> None:
        """RoundRobin has no selector: the fixed order starts with the Planner."""
        if self._mode == "round_robin":
            self._store.append(EventType.SPEAKER_SELECTED, "round_robin", {"next": "Planner"})

    # -- chat messages ---------------------------------------------------------------------
    def on_chat_message(self, message: BaseChatMessage) -> None:
        text = message_text(message)
        verdict = self._state.observe(message.id, message.source, text, message.models_usage)
        if not verdict.counted or message.id in self._mapped:
            return
        self._mapped.add(message.id)
        handler = {
            "Planner": self._planner,
            "Coder": self._coder,
            "Executor": self._executor,
            "Reviewer": self._reviewer,
        }[message.source]
        handler(text, verdict)
        if verdict.outcome is not None:
            self._terminal(verdict.outcome)
        elif self._mode == "round_robin":
            nxt = AGENTS[(AGENTS.index(message.source) + 1) % len(AGENTS)]
            self._store.append(EventType.SPEAKER_SELECTED, "round_robin", {"next": nxt})

    def _agent_message(
        self, source: str, event: str, outcome: str, tone: str, **extra: object
    ) -> None:
        self._store.append(
            EventType.AGENT_MESSAGE,
            source,
            {"event": event, "outcome": outcome, "tone": tone, **extra},
        )

    def _planner(self, text: str, verdict: MessageVerdict) -> None:
        steps = len(_NUMBERED.findall(text))
        outcome = f"Plan: {steps} steps" if steps else _first_line(text)
        self._agent_message("Planner", "agent_message", outcome, "", plan=text, index=verdict.index)

    def _coder(self, text: str, verdict: MessageVerdict) -> None:
        blocks = extract_python_blocks(text)
        if len(blocks) == 1:
            self._code_versions += 1
            code = blocks[0]
            self._store.append(
                EventType.CODE_GENERATED,
                "Coder",
                {
                    "version": self._code_versions,
                    "code": code,
                    "code_hash": code_hash(code),
                    "mark_line": 0,
                    "mark_kind": "",
                    **self._injected_flag(code_hash(code)),
                },
            )
            lines = len(code.splitlines())
            outcome = f"analysis.py v{self._code_versions} · {lines} lines"
            self._agent_message("Coder", "code_generated", outcome, "", index=verdict.index)
            return
        self._store.append(
            EventType.GUARDRAIL,
            "Coder",
            {"rule": "single_python_block", "outcome": "rejected", "blocks": len(blocks)},
        )
        self._agent_message(
            "Coder",
            "agent_message",
            f"no usable code: {len(blocks)} python blocks",
            "warn",
            index=verdict.index,
        )

    def _executor(self, text: str, verdict: MessageVerdict) -> None:
        last = self._state.last_exec
        ok = self._state.last_exec_ok
        status = last.status if last else "not_executed"
        code = "n/a" if last is None or last.exit_code is None else str(last.exit_code)
        outcome = f"ok · exit {code}" if ok else f"{status} · exit {code}"
        self._agent_message(
            "Executor", "exec_result", outcome, "ok" if ok else "bad", index=verdict.index
        )

    def _reviewer(self, text: str, verdict: MessageVerdict) -> None:
        if verdict.approved:
            self._agent_message(
                "Reviewer", "reviewer_approved", "APPROVED", "ok", index=verdict.index
            )
            self._store.append(
                EventType.REVIEWER_APPROVED, "Reviewer", {"text": text, "message": verdict.index}
            )
            return
        if verdict.approval_ignored:
            self._store.append(
                EventType.GUARDRAIL,
                "Reviewer",
                {"rule": "approval_requires_successful_execution", "outcome": "ignored"},
            )
        issues = len(_NUMBERED.findall(text))
        self._store.append(EventType.REVIEW_FEEDBACK, "Reviewer", {"text": text, "issues": issues})
        outcome = f"{issues} issues" if issues else _first_line(text)
        self._agent_message("Reviewer", "review_feedback", outcome, "warn", index=verdict.index)

    # -- terminal events -------------------------------------------------------------------
    def _terminal(self, outcome: RunOutcome) -> None:
        if self._terminal_emitted or outcome is RunOutcome.REVIEWER_APPROVED:
            self._terminal_emitted = True
            return
        self._terminal_emitted = True
        if outcome is RunOutcome.ERROR:
            self._store.append(
                EventType.RUN_ERROR, "app", {"reason": self._state.outcome_detail or "error"}
            )
            return
        self._store.append(
            EventType.LIMIT_REACHED,
            "app",
            {
                "count": self._state.agent_messages,
                "limit": _LIMIT_KIND[outcome],
                "max_messages": self._state.max_messages,
                "total_tokens": self._state.total_tokens,
                "max_tokens": self._state.max_tokens,
                "reason": outcome.value,
            },
        )

    def finish(self, result: TaskResult | None = None, error: str | None = None) -> RunOutcome:
        """Emit the closing events. Call exactly once, after the stream ended."""
        if error is not None:
            self._state.finish(RunOutcome.ERROR, error)
        elif self._state.outcome is None:
            self._state.finish(RunOutcome.ERROR, "team stopped without a run outcome")
        outcome = self._state.outcome
        if outcome is None:  # pragma: no cover - finish() above always sets one
            raise RuntimeError("run finished without an outcome")
        self._terminal(outcome)
        self._store.append(
            EventType.TERMINATED,
            "app",
            {
                "reason": outcome.value,
                "detail": self._state.outcome_detail,
                "stop_reason": result.stop_reason if result else None,
                "messages": self._state.agent_messages,
                "input_tokens": self._state.input_tokens,
                "output_tokens": self._state.output_tokens,
                "usage_by_source": {
                    k: {"input_tokens": v[0], "output_tokens": v[1], "calls": v[2]}
                    for k, v in self._state.usage_by_source.items()
                },
            },
        )
        return outcome

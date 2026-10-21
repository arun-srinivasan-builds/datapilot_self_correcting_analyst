"""T-TERM-1..5 (PRP §3.2): termination contract on the installed AutoGen 0.7.5, no live calls."""

from __future__ import annotations

import pytest
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import TaskResult, TerminationCondition
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_agentchat.messages import BaseChatMessage, StopMessage, TextMessage
from autogen_agentchat.teams import RoundRobinGroupChat

from datapilot.agents.termination import (
    RunOutcome,
    RunState,
    RunTerminator,
    is_standalone_approval,
)
from tests.agents.helpers import ERR, OK, client, run_script


async def test_t_term_1_task_message_excluded_and_cap_is_exactly_12():
    # never approves, every execution succeeds: only the cap can end this run
    run = await run_script("P C E✓ R " * 4, "round_robin")
    assert run.outcome is RunOutcome.LIMIT_REACHED
    assert len(run.of("agent_message")) == 12  # the task message is not one of them
    assert run.canvas.message_count == 12 and run.canvas.violations == ()
    assert run.of("run_started")[0].payload["question"]  # the task exists but is not counted


async def test_t_term_1_library_counter_counts_the_task_message_so_it_is_not_used():
    """Informational contract: MaxMessageTermination(12) would stop after only 11 agent messages."""
    agents = [AssistantAgent(n, client([f"{n} says hi"] * 20)) for n in ("A", "B")]
    team = RoundRobinGroupChat(agents, termination_condition=MaxMessageTermination(5))
    result = await team.run(task="the task")
    assert isinstance(result, TaskResult)
    sources = [m.source for m in result.messages]
    assert sources[0] == "user"
    assert len([s for s in sources if s != "user"]) == 4  # 5 reached with the task included


@pytest.mark.parametrize(
    ("mode", "script", "count", "outcome"),
    [
        ("selector", "P C E✗ C E✗ C E✓ R C E✓ R!", 11, RunOutcome.REVIEWER_APPROVED),
        ("selector", "P C E✓ R C E✓ R C E✗ C E✓ R!", 12, RunOutcome.REVIEWER_APPROVED),
        ("round_robin", "P C E✗ R P C E✓ R P C E✓ R!", 12, RunOutcome.REVIEWER_APPROVED),
        ("selector", "P C E✗ C E✗ C E✗ C E✓ R C E✓ R!", 12, RunOutcome.LIMIT_REACHED),
    ],
)
async def test_t_term_2_boundary_approval_on_11_and_12_and_no_13th_message(
    mode, script, count, outcome
):
    run = await run_script(script, mode)
    assert run.outcome is outcome
    assert len(run.of("agent_message")) == count
    assert run.canvas.message_count <= 12
    # no 13th message ever reached the replay clients' queues
    assert run.clients.coder.total_usage().prompt_tokens > 0
    assert len(run.of("agent_message")) <= 12


async def test_t_term_3_termination_is_evaluated_per_message_one_message_per_turn():
    deltas: list[int] = []

    class Spy(TerminationCondition):
        def __init__(self) -> None:
            self._t = False

        @property
        def terminated(self) -> bool:
            return self._t

        async def __call__(self, messages):
            deltas.append(len(messages))
            if len(deltas) >= 6:
                self._t = True
                return StopMessage(content="spy", source="spy")
            return None

        async def reset(self) -> None:
            self._t = False

    agents = [AssistantAgent(n, client(["x"] * 10)) for n in ("A", "B", "C")]
    await RoundRobinGroupChat(agents, termination_condition=Spy()).run(task="t")
    assert deltas == [1] * 6  # the task, then exactly one chat message per speaking turn


async def test_t_term_3_late_messages_after_the_outcome_are_not_counted():
    state = RunState(max_messages=2)
    terminator = RunTerminator(state)
    msgs = [TextMessage(content=f"m{i}", source="Planner") for i in range(4)]
    stop = await terminator(msgs)  # one batch with four messages: truncated at the cap
    assert stop is not None and stop.content == "LIMIT_REACHED"
    assert state.agent_messages == 2


@pytest.mark.parametrize(
    "text",
    [
        "NOT APPROVED",
        "APPROVED.",
        "approved",
        "Looks fine. APPROVED!",
        "```\nAPPROVED\n```",
        "```text\nresult\nAPPROVED",  # unclosed fence: APPROVED is inside it
        "APPROVED\nbut wait, one more thing",
        "",
    ],
)
def test_t_term_4_non_standalone_approvals_are_rejected(text):
    assert not is_standalone_approval(text)


@pytest.mark.parametrize("text", ["APPROVED", "All good.\nAPPROVED", "```x```\nOK\n\nAPPROVED\n\n"])
def test_t_term_4_standalone_approval_is_accepted(text):
    assert is_standalone_approval(text)


async def test_t_term_4_planner_and_executor_approved_text_never_terminates():
    planner = ["1) plan\nAPPROVED"] * 3  # Planner says APPROVED: ignored
    ok_stdout = OK.__class__("ok", 0, stdout="APPROVED")  # Executor stdout is APPROVED: ignored
    run = await run_script(
        "P C E✓ R P C E✓ R!", "round_robin", planner=planner, execs=[ok_stdout, ok_stdout]
    )
    assert run.outcome is RunOutcome.REVIEWER_APPROVED
    assert run.letters == "PCERPCER"  # only the Reviewer's second reply ended it


async def test_t_term_4_not_approved_and_fenced_approval_do_not_terminate():
    reviewer = ["NOT APPROVED", "```\nAPPROVED\n```", "Fine.\nAPPROVED"]
    run = await run_script("P C E✓ R C E✓ R C E✓ R", "selector", reviewer=reviewer)
    assert run.outcome is RunOutcome.REVIEWER_APPROVED
    assert run.letters == "PCERCERCER"


async def test_t_term_4_approval_after_failed_execution_is_ignored_but_counted():
    # RoundRobin sends E✗ to the Reviewer, who wrongly says APPROVED
    run = await run_script(
        "P C E✗ R P C E✓ R",
        "round_robin",
        reviewer=["Looks fine.\nAPPROVED", "Now it is fine.\nAPPROVED"],
    )
    assert run.outcome is RunOutcome.REVIEWER_APPROVED
    assert run.letters == "PCERPCER"  # the first APPROVED counted as message 4, did not terminate
    guard = [e for e in run.of("guardrail") if e.payload["rule"].startswith("approval_requires")]
    assert len(guard) == 1 and run.of("reviewer_approved")[0].payload["message"] == 8
    assert run.canvas.violations == ()


async def test_t_term_5_task_result_shape_and_outcome_for_every_end_state():
    cases = {
        RunOutcome.REVIEWER_APPROVED: await run_script("P C E✓ R!"),
        RunOutcome.LIMIT_REACHED: await run_script("P C E✓ R " * 4, "round_robin"),
    }
    for expected, run in cases.items():
        assert run.outcome is expected
        done = run.of("terminated")[0]
        assert done.payload["reason"] == expected.value
        assert (
            done.payload["stop_reason"] == expected.value
        )  # StopMessage.content from RunTerminator
        assert done.payload["messages"] == len(run.of("agent_message"))


async def test_t_term_5_token_budget_refusal_ends_without_a_task_result():
    run = await run_script("P C E✓ R!", max_tokens=5)
    assert run.outcome is RunOutcome.TOKEN_BUDGET_EXHAUSTED
    done = run.of("terminated")[0]
    assert done.payload["reason"] == "TOKEN_BUDGET_EXHAUSTED"
    assert done.payload["stop_reason"] is None  # the stream raised: there is no TaskResult
    assert done.payload["messages"] == 0  # the very first model call was refused


def test_token_budget_after_a_message_is_checked_after_approval():
    state = RunState(max_tokens=10)
    state.add_usage(20, 0)
    verdict = state.observe("m1", "Planner", "plan", None)
    assert verdict.outcome is RunOutcome.TOKEN_BUDGET_EXHAUSTED
    state2 = RunState(max_tokens=10)
    state2.record_exec("ok", 0)
    state2.add_usage(20, 0)
    approved = state2.observe("m2", "Reviewer", "fine\nAPPROVED", None)
    assert approved.outcome is RunOutcome.REVIEWER_APPROVED  # approval beats budget exhaustion


async def test_t_term_5_reset_does_not_reset_the_counter():
    state = RunState()
    terminator = RunTerminator(state)
    await terminator([TextMessage(content="x", source="Planner")])
    await terminator.reset()
    assert state.agent_messages == 1


def test_terminator_ignores_non_chat_events_and_unknown_sources():
    state = RunState()
    msg = TextMessage(content="hi", source="user")
    assert isinstance(msg, BaseChatMessage)
    verdict = state.observe(msg.id, msg.source, msg.content, None)
    assert not verdict.counted and state.agent_messages == 0


async def test_error_scenario_marks_no_approval(monkeypatch):
    run = await run_script("P C E✗ C E✗ C E✗ C E✗ C E✗ C E✗", execs=[ERR] * 6)
    assert run.outcome is RunOutcome.LIMIT_REACHED
    assert run.canvas.phase == "limit_reached"

"""Routing guard, executor bridge, event mapping, runner controls (real AutoGen, scripted LLM)."""

from __future__ import annotations

import asyncio
import json

import pytest
from autogen_agentchat.messages import TextMessage
from autogen_core import CancellationToken
from autogen_core.code_executor import CodeBlock

from datapilot.agents.executor import MAX_FIELD_CHARS, ObservedCodeExecutor, format_result
from datapilot.agents.routing import GuardedSelector
from datapilot.agents.runner import RunControl
from datapilot.agents.termination import RunOutcome, RunState
from datapilot.events import EventStore, EventType, reduce_events
from datapilot.sandbox.contracts import ExecutionResult, SandboxUnavailableError
from tests.agents.helpers import ERR, OK, STDERR, ScriptedBackend, run_script

CODE = "```python\nprint(1)\n```"


def msg(source: str, text: str = "x") -> TextMessage:
    return TextMessage(content=text, source=source)


# ---------------------------------------------------------------- routing (pure) -------------
def test_selector_routes_every_row_of_the_table():
    state = RunState()
    sel = GuardedSelector(state)
    task = msg("user", "task")
    plan, code = msg("Planner"), msg("Coder", CODE)
    assert sel([task]) == "Planner"
    assert sel([task, plan]) == "Coder"
    assert sel([task, plan, code]) == "Executor"
    # executor result comes from the hook: failed -> Coder
    state.record_exec("error", 1)
    assert sel([task, plan, code, msg("Executor")]) == "Coder"
    state2 = RunState()
    state2.record_exec("ok", 0)
    assert GuardedSelector(state2)([task, plan, code, msg("Executor")]) == "Reviewer"
    # reviewer not approving -> Coder
    state3 = RunState()
    state3.record_exec("ok", 0)
    ex = msg("Executor")
    rev = msg("Reviewer", "1. fix")
    assert GuardedSelector(state3)([task, plan, code, ex, rev]) == "Coder"


@pytest.mark.parametrize("text", ["no code at all", f"{CODE}\n{CODE}", "```sh\nls\n```"])
def test_coder_without_exactly_one_python_block_goes_back_to_coder(text):
    sel = GuardedSelector(RunState())
    assert sel([msg("user"), msg("Planner"), msg("Coder", text)]) == "Coder"


def test_executor_that_ran_nothing_routes_to_coder_never_reviewer():
    state = RunState()  # no exec recorded -> "No code blocks found" turn
    sel = GuardedSelector(state)
    assert (
        sel([msg("user"), msg("Planner"), msg("Coder", "x"), msg("Executor", "No code")]) == "Coder"
    )
    assert state.last_exec.status == "not_executed"


async def test_executor_failure_never_reaches_reviewer_in_guarded_mode():
    run = await run_script("P C E✗ C E✓ R!")
    assert run.letters == "PCECER"
    repairs = run.of("repair_routed")
    assert len(repairs) == 1 and repairs[0].payload["attempt"] == 1


async def test_round_robin_baseline_sends_error_to_reviewer_and_is_labelled():
    run = await run_script("P C E✗ R P C E✓ R!", "round_robin")
    assert run.letters == "PCERPCER"
    assert run.of("repair_routed") == []  # nothing is rerouted in the baseline
    assert run.of("run_started")[0].payload["mode"] == "round_robin"


# ---------------------------------------------------------------- executor bridge ------------
async def exec_blocks(blocks, backend):
    state, store = RunState(), EventStore("r")
    executor = ObservedCodeExecutor(backend, state, store, "r")
    result = await executor.execute_code_blocks(blocks, CancellationToken())
    return result, state, store


async def test_executor_records_structured_result_and_returns_stderr_verbatim():
    backend = ScriptedBackend([ERR])
    result, state, store = await exec_blocks([CodeBlock("print(1)", "python")], backend)
    assert result.exit_code == 1 and STDERR in result.output
    assert state.last_exec.status == "error" and not state.last_exec_ok
    types = [e.type for e in store.snapshot()]
    assert types == [EventType.EXEC_STARTED, EventType.EXEC_RESULT]
    assert store.snapshot()[1].payload["stderr"] == STDERR


@pytest.mark.parametrize(
    "blocks", [[], [CodeBlock("a", "python"), CodeBlock("b", "python")], [CodeBlock("ls", "sh")]]
)
async def test_executor_rejects_anything_but_one_python_block_without_running(blocks):
    backend = ScriptedBackend([OK])
    result, state, store = await exec_blocks(blocks, backend)
    assert backend.codes == [] and result.exit_code == 2
    assert state.last_exec.status == "rejected"
    assert [e.type for e in store.snapshot()][0] is EventType.GUARDRAIL


async def test_infra_failure_ends_the_run_as_error_not_as_a_code_defect():
    class Down:
        async def run(self, code, *, run_id):
            raise SandboxUnavailableError("broker unreachable")

    run = await run_script("P C E✓ R!", backend=Down())
    assert run.outcome is RunOutcome.ERROR
    assert run.canvas.phase == "error"
    assert "broker unreachable" in run.of("run_error")[0].payload["reason"]


def test_long_output_is_tail_truncated_with_a_marker():
    text = format_result(ExecutionResult("error", 1, stderr="x" * (MAX_FIELD_CHARS + 500) + "TAIL"))
    assert "504 earlier" in text and text.rstrip().endswith("TAIL")


# ---------------------------------------------------------------- event mapping --------------
async def test_events_follow_the_real_order_and_feed_the_real_reducer():
    run = await run_script("P C E✗ C E✓ R!")
    types = run.types()
    assert types[0] == "run_started"
    # selector, then message, in order; execution events sit between Coder and Executor messages
    exec_idx = types.index("exec_started")
    coder_msg = max(
        i
        for i, e in enumerate(run.store.snapshot())
        if e.type.value == "agent_message" and e.source == "Coder" and i < exec_idx
    )
    assert coder_msg < exec_idx  # the Coder's message is recorded before its code executes
    assert types.index("repair_routed") > types.index("exec_result")
    assert types[-2:] == ["reviewer_approved", "terminated"] or types[-3:-1] == [
        "reviewer_approved",
        "usage",
    ]
    canvas = run.canvas
    assert canvas.phase == "approved" and canvas.message_count == 6
    assert canvas.repair_attempts == 1 and canvas.last_exec_ok is True
    assert canvas.human == "none" and not canvas.fully_verified  # Reviewer != human approval
    assert canvas.violations == ()
    assert [e.seq for e in run.store.snapshot()] == list(range(1, len(run.store) + 1))


async def test_code_and_usage_events_carry_real_data_and_serialize():
    run = await run_script("P C E✓ R!")
    codes = run.of("code_generated")
    assert codes[0].payload["code"].startswith("# version 1")
    assert len(codes[0].payload["code_hash"]) == 12
    usage = run.of("usage")
    assert usage and all(u.payload["input_tokens"] > 0 for u in usage)  # Planner/Coder/Reviewer
    assert {u.source for u in usage} == {"Planner", "Coder", "Reviewer"}  # Executor has no usage
    assert canvas_tokens(run) == (
        run.of("terminated")[0].payload["input_tokens"],
        run.of("terminated")[0].payload["output_tokens"],
    )
    json.dumps([e.to_dict() for e in run.store.snapshot()])


def canvas_tokens(run):
    c = reduce_events(run.store.snapshot())
    return c.input_tokens, c.output_tokens


async def test_invalid_coder_output_is_a_guardrail_event_and_costs_budget():
    run = await run_script(
        "P C C E✓ R!", coder=["I will not write code.", "```python\nprint(1)\n```"]
    )
    assert run.outcome is RunOutcome.REVIEWER_APPROVED
    assert run.letters == "PCCER"
    assert run.of("guardrail")[0].payload["rule"] == "single_python_block"


async def test_token_budget_exhaustion_is_reported_as_a_distinct_unapproved_limit():
    run = await run_script("P C E✓ R!", max_tokens=5)
    assert run.outcome is RunOutcome.TOKEN_BUDGET_EXHAUSTED
    limit = run.of("limit_reached")[0]
    assert limit.payload["limit"] == "tokens" and limit.payload["max_tokens"] == 5
    assert run.canvas.phase == "limit_reached"


# ---------------------------------------------------------------- runner controls ------------
class SlowBackend:
    async def run(self, code, *, run_id):
        await asyncio.sleep(30)
        return OK


async def test_wall_clock_timeout_ends_the_run_as_timeout():
    run = await run_script("P C E✓ R!", backend=SlowBackend(), timeout_seconds=1)
    assert run.outcome is RunOutcome.TIMEOUT
    assert run.of("limit_reached")[0].payload["limit"] == "time"
    assert run.of("terminated")[0].payload["reason"] == "TIMEOUT"
    assert run.canvas.phase == "limit_reached" and not run.canvas.reviewer_verified


async def test_user_stop_is_distinct_from_timeout():
    control = RunControl()
    asyncio.get_running_loop().call_later(0.5, control.stop)
    run = await run_script("P C E✓ R!", backend=SlowBackend(), control=control)
    assert run.outcome is RunOutcome.STOPPED
    assert run.of("limit_reached")[0].payload["limit"] == "stopped"


async def test_unexpected_exception_becomes_run_error_event():
    class Boom:
        async def run(self, code, *, run_id):
            raise ValueError("backend bug")

    run = await run_script("P C E✓ R!", backend=Boom())
    assert run.outcome is RunOutcome.ERROR
    assert run.canvas.phase == "error"
    assert "backend bug" in run.of("run_error")[0].payload["reason"]


# ---------------------------------------------------------------- token budget (C6) ----------
async def test_budget_counts_every_model_call_including_selector_calls():
    from autogen_core.models import UserMessage

    from datapilot.agents.budget import BudgetedClient, TokenBudgetExhaustedError
    from tests.agents.helpers import client

    state = RunState(max_tokens=100_000)
    wrapped = BudgetedClient(client(["hi", "there"]), state, "selector")
    await wrapped.create([UserMessage(content="select a speaker", source="selector")])
    first = state.total_tokens
    assert first > 0 and state.input_tokens > 0
    await wrapped.create([UserMessage(content="again", source="selector")])
    assert state.total_tokens > first
    tiny = RunState(max_tokens=3)
    with pytest.raises(TokenBudgetExhaustedError):
        await BudgetedClient(client(["x"]), tiny, "Planner").create(
            [UserMessage(content="word " * 50, source="u")]
        )
    assert tiny.token_blocked and tiny.outcome is RunOutcome.TOKEN_BUDGET_EXHAUSTED


async def test_run_total_tokens_equals_the_sum_of_reported_usage():
    run = await run_script("P C E✓ R!")
    total = run.of("terminated")[0].payload
    per_message = sum(
        e.payload["input_tokens"] + e.payload["output_tokens"] for e in run.of("usage")
    )
    assert total["input_tokens"] + total["output_tokens"] == per_message > 0

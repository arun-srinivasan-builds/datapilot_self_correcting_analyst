"""Stage 1: pins the AutoGen 0.7.5 behaviours M3 relies on (findings in docs/evidence/m3)."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from autogen_agentchat.agents import CodeExecutorAgent, UserProxyAgent
from autogen_agentchat.messages import CodeExecutionEvent, TextMessage
from autogen_core import CancellationToken
from autogen_core.code_executor import CodeResult

from datapilot.agents.codeblocks import extract_python_blocks
from datapilot.agents.executor import ObservedCodeExecutor
from datapilot.agents.termination import RunState
from datapilot.events import EventStore
from tests.agents.helpers import OK, ScriptedBackend, run_script

ROOT = Path(__file__).resolve().parents[2]


def make_agent(sources=("Coder",)) -> tuple[CodeExecutorAgent, ScriptedBackend]:
    backend = ScriptedBackend([OK] * 5)
    executor = ObservedCodeExecutor(backend, RunState(), EventStore("r"), "r")
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="No approval function set")
        agent = CodeExecutorAgent(
            "Executor",
            code_executor=executor,
            sources=list(sources),
            supported_languages=["python"],
        )
    return agent, backend


async def stream(agent, messages):
    return [m async for m in agent.on_messages_stream(messages, CancellationToken())]


async def test_u3_executor_without_model_client_yields_one_text_message_and_no_code_events():
    agent, backend = make_agent()
    items = await stream(agent, [TextMessage(content="```python\nprint(1)\n```", source="Coder")])
    kinds = [type(i).__name__ for i in items]
    assert kinds == ["Response"]  # no CodeGenerationEvent / CodeExecutionEvent
    assert not isinstance(items[0].chat_message, CodeExecutionEvent)
    assert "exit_code: 0" in items[0].chat_message.content and backend.codes == ["print(1)\n"]


async def test_executor_text_carries_no_structured_status_so_routing_cannot_parse_it():
    agent, _ = make_agent()
    (response,) = await stream(agent, [TextMessage(content="```python\nx\n```", source="Coder")])
    assert isinstance(response.chat_message, TextMessage)
    assert not hasattr(response.chat_message, "result")  # exit status must come from our hook


async def test_no_code_block_still_produces_a_counted_text_message():
    agent, backend = make_agent()
    (response,) = await stream(agent, [TextMessage(content="just prose", source="Coder")])
    assert response.chat_message.content == CodeExecutorAgent.NO_CODE_BLOCKS_FOUND_MESSAGE
    assert backend.codes == []


async def test_sources_filter_ignores_code_from_other_agents():
    agent, backend = make_agent()
    text = "```python\nprint('planner')\n```"
    await stream(agent, [TextMessage(content=text, source="Planner")])
    assert backend.codes == []


async def test_all_python_blocks_of_scanned_messages_are_executed_together_so_we_reject_extras():
    agent, backend = make_agent()
    two = "```python\na=1\n```\n```python\nb=2\n```"
    items = await stream(agent, [TextMessage(content=two, source="Coder")])
    assert backend.codes == []  # ObservedCodeExecutor refuses != 1 block
    assert "rejected" in items[0].chat_message.content


@pytest.mark.parametrize(
    "text",
    [
        "```python\nprint(1)\n```",
        "```Python\nprint(1)\n```",
        "```py\nprint(1)\n```",
        "```sh\nls\n```",
        "```python\na\n```\ntext\n```python\nb\n```",
        "no fences",
    ],
)
def test_our_block_extraction_matches_the_library(text):
    agent, _ = make_agent()
    library = [b.code for b in agent._extract_markdown_code_blocks(text)]
    assert extract_python_blocks(text) == library


async def test_each_executor_turn_runs_only_the_latest_coder_code():
    run = await run_script("P C E✗ C E✗ C E✓ R!")
    assert run.backend.codes == [
        "# version 1\nprint(1)\n",
        "# version 2\nprint(2)\n",
        "# version 3\nprint(3)\n",
    ]


async def test_coder_receives_executor_stderr_verbatim_in_its_next_input():
    run = await run_script("P C E✗ C E✓ R!")
    from tests.agents.helpers import STDERR

    seen = run.clients.coder.create_calls  # exact inputs the Coder's model client received
    assert len(seen) == 2
    second_input = "\n".join(str(getattr(m, "content", "")) for m in seen[1]["messages"])
    assert STDERR in second_input


async def test_user_proxy_blocks_on_its_input_function_and_returns_the_decision_as_a_message():
    async def decide(prompt: str, token=None) -> str:
        return "APPROVE"

    proxy = UserProxyAgent("User", input_func=decide)
    reply = await proxy.on_messages(
        [TextMessage(content="approve?", source="Reviewer")], CancellationToken()
    )
    assert reply.chat_message.source == "User" and reply.chat_message.content == "APPROVE"
    # the human stage lives outside the team, so it can never enter the 12-message budget
    state = RunState()
    msg = reply.chat_message
    assert not state.observe(msg.id, msg.source, msg.content, None).counted


def test_message_ids_are_unique_and_stable():
    a, b = TextMessage(content="x", source="Coder"), TextMessage(content="x", source="Coder")
    assert a.id != b.id and a.id == a.id


def test_codeblock_executor_signature_uses_the_cancellation_token_keyword():
    import inspect

    sig = inspect.signature(ObservedCodeExecutor.execute_code_blocks)
    assert "cancellation_token" in sig.parameters
    assert CodeResult(exit_code=0, output="").exit_code == 0


def test_only_ui_live_module_may_import_agent_or_execution_code():
    """Live runs start through `ui/live.py` only; every other UI module stays presentation-only."""
    import ast

    banned = (
        "autogen_agentchat", "autogen_core", "autogen_ext", "openai", "datapilot.sandbox",
        "datapilot.agents", "datapilot.session", "datapilot.faults", "datapilot.events.mapping",
    )  # fmt: skip
    offenders: dict[str, list[str]] = {}
    for path in (ROOT / "src" / "datapilot" / "ui").rglob("*.py"):
        if path.name == "live.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            bad = [n for n in names if n.startswith(banned) and n != "datapilot.agents.usage"]
            if bad:
                offenders.setdefault(path.name, []).extend(bad)
    assert offenders == {}


async def test_stage5_finding_executor_runs_only_the_latest_coder_message():
    """Stale blocks from earlier unusable Coder replies are never bundled with a valid script."""
    from datapilot.agents.participants import LatestCoderExecutorAgent

    backend = ScriptedBackend([OK] * 3)
    executor = ObservedCodeExecutor(
        backend, RunState(), EventStore("r"), "r", require_results=False
    )
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="No approval function set")
        agent = LatestCoderExecutorAgent(
            "Executor", code_executor=executor, sources=["Coder"], supported_languages=["python"]
        )
    stale_two = "```python\na=1\n```\n```python\nb=2\n```"
    messages = [
        TextMessage(content=stale_two, source="Coder"),
        TextMessage(content="no code here", source="Coder"),
        TextMessage(content="```python\nprint('latest')\n```", source="Coder"),
    ]
    await stream(agent, messages)
    assert backend.codes == ["print('latest')\n"]  # exactly the newest script, nothing stale
    # and with nothing from the Coder, nothing runs
    assert (
        await agent.extract_code_blocks_from_messages([TextMessage(content="x", source="Planner")])
        == []
    )


async def test_stage6_injected_message_replaces_the_coders_own_memory():
    """No live sandbox needed: the injecting Coder's memory, response and event all agree."""
    from autogen_core.models import AssistantMessage

    from datapilot.agents.participants import FaultInjectingCoder
    from datapilot.config import Settings
    from datapilot.faults import FaultInjectionError, FaultInjector
    from tests.agents.helpers import client

    reply = 'Script:\n```python\nx = df["units"]\n```'
    settings = Settings(_env_file=None, app_env="test", fault_injection="missing_column")
    injector = FaultInjector.authorized(settings, "missing_column")
    store = EventStore("r")
    injector.attach(store, {})
    coder = FaultInjectingCoder("Coder", client([reply, reply]), injector=injector)
    task = TextMessage(content="go", source="user")
    response = await coder.on_messages([task], CancellationToken())
    assert (
        'df["qty"]' in response.chat_message.content
        and 'df["units"]' not in response.chat_message.content
    )
    history = await coder._model_context.get_messages()
    assistant = [m for m in history if isinstance(m, AssistantMessage)]
    assert [m.content for m in assistant] == [
        response.chat_message.content
    ]  # memory == what was sent
    assert [e.type.value for e in store.snapshot()] == ["test_fault_injected"]
    second = await coder.on_messages([task], CancellationToken())  # times=1: left alone afterwards
    assert second.chat_message.content == reply

    broken = FaultInjectingCoder(
        "Coder2",
        client([reply]),
        injector=FaultInjector.authorized(settings, "missing_column"),
    )
    broken._injector.attach(EventStore("r2"), {})

    async def no_clear() -> None:  # a context that cannot be rewritten must be refused, not ignored
        return None

    broken._model_context.clear = no_clear  # type: ignore[method-assign]
    with pytest.raises(FaultInjectionError, match="does not match"):
        await broken.on_messages([task], CancellationToken())

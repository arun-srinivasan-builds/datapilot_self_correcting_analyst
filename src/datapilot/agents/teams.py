"""Team assembly. Production = guarded SelectorGroupChat; RoundRobin = labelled test baseline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from autogen_agentchat.teams import BaseGroupChat, RoundRobinGroupChat, SelectorGroupChat
from autogen_core.models import ChatCompletionClient

from datapilot.agents.budget import BudgetedClient
from datapilot.agents.executor import ObservedCodeExecutor
from datapilot.agents.participants import RoleClients, build_participants
from datapilot.agents.routing import GuardedSelector
from datapilot.agents.termination import RunState, RunTerminator
from datapilot.events import EventStore
from datapilot.events.mapping import EventMapper
from datapilot.faults import FaultInjector
from datapilot.sandbox.contracts import ExecutionBackend

Mode = Literal["selector", "round_robin"]
BASELINE_MODE: Mode = "round_robin"
PRODUCTION_MODE: Mode = "selector"


@dataclass(frozen=True, slots=True)
class BuiltTeam:
    team: BaseGroupChat
    mapper: EventMapper
    state: RunState


def build_team(
    mode: Mode,
    *,
    clients: RoleClients,
    selector_client: ChatCompletionClient,
    backend: ExecutionBackend,
    store: EventStore,
    state: RunState,
    run_id: str,
    require_results: bool = True,
    completion_ceiling: int | None = None,
    fault: FaultInjector | None = None,
) -> BuiltTeam:
    """A fresh team per run (teams keep conversation state; a new run is a new team and state)."""
    mapper = EventMapper(store, state, mode)
    executor = ObservedCodeExecutor(backend, state, store, run_id, require_results=require_results)

    def wrap(client: ChatCompletionClient, source: str) -> BudgetedClient:
        return BudgetedClient(client, state, source, store, completion_ceiling)

    budgeted = RoleClients(
        wrap(clients.planner, "Planner"),
        wrap(clients.coder, "Coder"),
        wrap(clients.reviewer, "Reviewer"),
    )
    if fault is not None:  # TEST ONLY: the injector was created through faults.authorize()
        fault.attach(store, state.injected_hashes)
    parts = build_participants(budgeted, executor, fault)
    terminator = RunTerminator(state, on_message=mapper.on_chat_message)
    # Defensive backstop only: the app-owned terminator ends every run long before this.
    backstop = max(2 * state.max_messages, state.max_messages + 8)
    team: BaseGroupChat
    if mode == "selector":
        team = SelectorGroupChat(
            parts.in_cycle_order(),
            model_client=wrap(selector_client, "selector"),
            termination_condition=terminator,
            max_turns=backstop,
            selector_func=GuardedSelector(state, store),
            allow_repeated_speaker=True,
        )
    elif mode == "round_robin":
        team = RoundRobinGroupChat(
            parts.in_cycle_order(), termination_condition=terminator, max_turns=backstop
        )
    else:  # pragma: no cover - guarded by the Literal type
        raise ValueError(f"unknown mode: {mode}")
    return BuiltTeam(team, mapper, state)

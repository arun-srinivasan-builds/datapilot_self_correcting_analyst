# M3 Stage 1: AutoGen 0.7.5 contract findings

Method: read the installed source (`.venv/Lib/site-packages/autogen_agentchat`), then ran scripted
experiments with `ReplayChatCompletionClient` (no live model calls) and pinned every finding as a
test in `tests/agents/test_autogen_contracts.py` or `tests/agents/test_t_term.py`.
Nothing here used a container runtime; `ScriptedBackend` in tests is a scripted stand-in and is not
sandbox evidence.

| ID | Question | Finding | Pinned by |
|---|---|---|---|
| U2a | Is the task message passed to termination conditions? | **Yes.** The first call receives the task (`source="user"`). `MaxMessageTermination(5)` therefore stops after 4 agent messages. The library counter cannot implement "12 agent messages" | `test_t_term_1_library_counter_counts_the_task_message...` |
| U2b | Per message or per batch? | **Per message.** Every call received exactly one message (task, then one per speaking turn) | `test_t_term_3_termination_is_evaluated_per_message...` |
| U2c | Can one turn emit two chat messages? | Not for these agents (AssistantAgent without tools, CodeExecutorAgent without model). If a batch ever had several, `RunState` stops counting at the cap | `test_t_term_3_late_messages_after_the_outcome...` |
| U2d | Does the manager call `reset()` on the condition? | Yes, after it fires. `RunTerminator.reset()` is a deliberate no-op: the counter never resets within a run; a new run builds a new `RunState` | `test_t_term_5_reset_does_not_reset_the_counter` |
| U3 | `CodeExecutionEvent` without a model client? | **Not emitted.** The agent yields a single `TextMessage(content=output)`; no exit code, no structured result. Structured status therefore comes from `ObservedCodeExecutor` (recorded in `RunState` + events). Routing never parses executor text | `test_u3_executor_without_model_client...`, `test_executor_text_carries_no_structured_status...` |
| U3b | Executor with no code block | Emits a counted `TextMessage("No code blocks found...")` and runs nothing. `RunState` marks `not_executed`, which routes to the Coder and blocks approval | `test_no_code_block_still_produces...`, `test_executor_that_ran_nothing_routes_to_coder...` |
| U3c | Which blocks run? | **All** python blocks of all scanned `Coder` messages are passed together. `ObservedCodeExecutor` rejects anything but exactly one python block (guardrail event, nothing executed). `sources=["Coder"]` ignores other agents' code | `test_all_python_blocks...`, `test_sources_filter...` |
| U3d | Executor call signature | The library calls `execute_code_blocks(code_blocks, cancellation_token=...)` by keyword; the parameter must be named `cancellation_token` | `test_codeblock_executor_signature...` |
| U4 | `TaskResult` / `stop_reason` | `TaskResult.messages` starts with the task message (`source="user"`); `stop_reason` is the `StopMessage.content` of the condition that fired. We use `RunOutcome` values, so `stop_reason == outcome` for approved / limit / token budget | `test_t_term_5_task_result_shape...` |
| A6 | `selector_func` and the LLM | With `selector_func` returning a name the selector model client is never called (its replay client has no responses and the runs pass). `allow_repeated_speaker=False` does not block a `selector_func` that returns the same speaker (Coder -> Coder) | all selector scenarios; `test_invalid_coder_output...` |
| A6b | Library events | With `emit_team_events=True` a `SelectSpeakerEvent(source="SelectorGroupChatManager")` is emitted even for `selector_func`. We do not rely on it: the selector itself records `speaker_selected` (source `selector`) in order | spike `scratchpad/spike1.py` (observed) |
| C-cancel | Cancellation | Cancelling the `CancellationToken` makes `run_stream` raise `CancelledError`. The runner maps it to `TIMEOUT` or `STOPPED` via `RunControl.reason`. `ObservedCodeExecutor` links the token to the in-flight backend call, so the backend must treat `CancelledError` as "kill the container" (Stage 4) | `test_wall_clock_timeout...`, `test_user_stop...` |
| UP | UserProxyAgent | Awaits its `input_func` and returns the decision as a `TextMessage` with the proxy's name. It is used outside the team, so it can never enter the 12-message budget | `test_user_proxy_blocks_on_its_input_function...` |
| ID | Message identity | Every chat message has a unique `id`. `RunState.observe` is idempotent per id, so the terminator and the event mapper always agree | `test_message_ids_are_unique...` |
| ORD | Event order | The manager applies the termination condition to a message before it selects the next speaker. Mapping chat messages from inside `RunTerminator` therefore records events in the order the team processed them (a stream consumer could lag behind the executor) | `test_events_follow_the_real_order...` |

## Deviations from the PRP text
1. PRP §3.1 returned `None` (LLM chooses) for a Coder message without code. The implementation routes
   such a message back to the Coder deterministically (with a `guardrail` event); `None` is only used
   for states that cannot occur. This protects the 12-message budget and keeps routing LLM-free.
2. Token exhaustion, wall-clock timeout and user stop are recorded as `limit_reached` events with a
   `limit` field (`messages` | `tokens` | `time` | `stopped`), so the existing reducer shows them as
   an UNAPPROVED stop that cannot be human-approved. The distinct reason is in `terminated.reason`.

## Not settled in Stage 1 (carried forward)
- Whether `gpt-6-luna` `completion_tokens` includes reasoning tokens (needs a live call; Stage 9).
- Selector fallback usage reconciliation (`RunState.add_usage` exists; wiring is Stage 5).
- Coder-context mutation for fault injection (Stage 6).

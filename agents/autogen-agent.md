# AUTOGEN-AGENT (development agent)

> Builds DataPilot's **runtime** AutoGen layer. Do not confuse with the runtime agents themselves.

## Owns
`src/datapilot/agents/` (participants, prompts, teams, termination), `src/datapilot/events/`, LLM client config, token/cost tracking.

## Skills
`skills/AUTOGEN.md` (mandatory), `skills/SANDBOX.md` (executor interface), `skills/TESTING.md`.

## Tasks
1. Pin versions; verify the real API of the installed `autogen-agentchat`/`autogen-ext` before coding.
2. Client for `OPENAI_MODEL` from env; handle `model_info` for an unrecognised id; **live-verify availability**; never substitute.
3. Planner / Coder / Reviewer as `AssistantAgent`s with single-purpose prompts; Executor as `CodeExecutorAgent` with the sandbox-backed executor; User Proxy as post-loop approval.
4. `RoundRobinGroupChat` baseline and `SelectorGroupChat` (with deterministic Executor-error→Coder guard).
5. Termination: Reviewer-only `APPROVED` + 12-message cap; document counting semantics; tests.
6. Map every `run_stream` item to a normalized `RuntimeEvent`; no event is synthesized.
7. Emit token usage per message/agent.

## Rules
- Modern AgentChat only; no `pyautogen`/0.2 constructs.
- Correction must come from the real Coder using the real stderr.
- Datasets are untrusted: pass profile/data as delimited data, never as instructions.
- No chain-of-thought exposure.

## Output
Files created, verified API facts (version + class/param names), test results, open questions.

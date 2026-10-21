# Generate PRP Command

You are the **DataPilot PRP Generator**. Turn `INITIAL.md` into a milestone-gated implementation blueprint for an AutoGen + Streamlit learning assignment.

## Input
Product definition: $ARGUMENTS (defaults to `INITIAL.md`).

## Read first
- `CLAUDE.md`
- `INITIAL.md` (all sections, esp. §5 workflow, §10 sandbox, §14 traceability, §15 decisions, §16 conflicts)
- `docs/SocialEagle_UseCase_Definitions.pdf` pp. 9–11 (authoritative; extract with `pdftotext -f 9 -l 11 -layout`)
- `agents/ORCHESTRATOR.md`
- All `skills/*.md`

## Preconditions (refuse to proceed if unmet)
1. Milestone 1 review has been approved by the user.
2. Open decisions D1–D8 in `INITIAL.md §15` are either resolved or explicitly accepted as "recommended".
3. Not a SaaS: do **not** introduce FastAPI, React, a database, auth, or payments.

## Step 1 — Parse
Extract: assignment problem; runtime agents; workflow + termination; ingestion; outputs; UI workspaces; Livewire; sandbox; guardrails/evals; tests; Docker/Traefik/VPS; stretch goals; acceptance criteria; open decisions.

## Step 2 — Verify the technical ground (read-only research; no installs unless the PRP milestone says so)
Record in the PRP, with sources/versions, answers to:
- AutoGen: exact pinned versions; `RoundRobinGroupChat`, `SelectorGroupChat` (`selector_func`, `candidate_func`), `TextMentionTermination` (`sources`?), `MaxMessageTermination` counting semantics, `CodeExecutorAgent`, custom `CodeExecutor` interface, `run_stream` message/event types, `UserProxyAgent` input handling.
- `OpenAIChatCompletionClient` requirements for an unrecognised model id (`model_info`).
- Streamlit↔async bridge options (thread + queue, `st.fragment(run_every)`, placeholders) and what HTML/CSS/SVG Streamlit permits.
- Sandbox isolation levels L2/L3/L4 (`skills/SANDBOX.md`): what the VPS can support, and the documented limitations of a long-running service versus a fresh container per execution. The PRP must state the chosen level honestly.

## Step 3 — Write `PRPs/datapilot-prp.md`

Required sections:

1. **Metadata** (version, date, complexity, milestones)
2. **Product overview + primary acceptance criterion** (genuine autonomous correction)
3. **Tech stack** with pinned versions and rationale
4. **Architecture** — component diagram; runtime-agent roles; message flow; termination state machine (APPROVED-by-Reviewer / limit / error); human-approval state separate
5. **Event model** — normalized runtime events (agent_started, message, code_generated, exec_started, exec_result, exec_error, repair_routed, review_feedback, approved, terminated, human_approved…) and exactly which AutoGen stream item produces each
6. **Modules** (each with files, interfaces, tests): ingestion · agents/teams · sandbox · events · reports (py/PNG/PDF) · UI workspaces · livewire · guardrails/evals/observability · config
7. **Milestones M1–M7** (refine if justified) each with: tasks, owner dev-agent, deliverables, **validation gate commands**, exit criteria, rework log hook
8. **Traceability matrix** carried from `INITIAL.md §14`, extended to concrete files/tests
9. **Test plan** — mocked-LLM unit suite, live suite, e2e auto-fix, sandbox isolation, viewport/screenshots, determinism
10. **Security & guardrails**
11. **Deployment plan** — Compose, healthchecks, Traefik labels (placeholders until inspected), rollback
12. **Risks & decisions** with owner and trigger
13. **Next step**: `/execute-prp PRPs/datapilot-prp.md --milestone M2`

## Output
Save to `PRPs/datapilot-prp.md`. Report: sections, milestones, modules, event types, open decisions, the verified API facts, and anything that contradicts INITIAL.md (propose resolution; never silently change assignment intent).
Do not commit.

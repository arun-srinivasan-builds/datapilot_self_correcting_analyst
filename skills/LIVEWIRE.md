# Agent Livewire Skill

> Live orchestration/observability canvas. **Every pixel of activity maps to a real runtime event.**

## Event → visual mapping (normalized `RuntimeEvent`)

| Event (source) | Visual |
|---|---|
| `run_started` (task submitted) | canvas armed, counter 0/12, lanes idle |
| `agent_active` (speaker begins/stream item from agent) | node glow/pulse while that agent is working |
| `message` (agent→next) | message appears in feed; connector animates once from sender to **actual** next speaker |
| `code_generated` (Coder code block) | code chip on Coder node; inspectable |
| `exec_started` / `exec_result ok` | Executor node active → success tick; stdout/artifacts inspectable |
| `exec_error` | Executor node error state + red error badge; stderr inspectable |
| `repair_routed` (Executor→Coder) | red→amber connector animation Executor→Coder; "repair attempt n" |
| `review_feedback` (Reviewer≠APPROVED) | amber connector Reviewer→Coder; feedback inspectable |
| `reviewer_approved` | Reviewer node approval state; terminates run |
| `limit_reached` | terminal state "Unapproved / limit 12/12" |
| `human_approved` / `human_rejected` | separate human-stage node state (distinct from Reviewer) |
| `guardrail` | small shield marker with outcome |
| `test_fault_injected` (test harness only) | persistent "TEST FAULT INJECTED" badge on the Coder node and timeline entry; never styled as a natural error |

Counter = count of real agent messages per the project definition (see AUTOGEN.md); never derived from elapsed time.

## Layout
Horizontal flow lanes on wide screens (Planner → Coder ⇄ Executor → Reviewer → Human), with loop-back arcs for repair/feedback; vertical lanes on narrow screens. Beside/below: live message feed, expandable execution timeline, inspector (code / stdout / stderr / feedback / guardrail / tokens).

Not acceptable: four static boxes with arrows.

## Implementation notes
- SVG + CSS classes toggled from event state (`.is-active`, `.is-error`, `.flow-repair`); animate with CSS `@keyframes`/transitions; one animation per real transfer.
- Render from an immutable event list → deterministic state (`reduce(events) → CanvasState`); unit-test the reducer with recorded event sequences.
- `prefers-reduced-motion`: replace pulses/flows with static state + text label.
- No `time.sleep`, no animation without an event, no percentages, no "typing" effects that imply progress.
- Don't display hidden reasoning; messages are only what agents actually emitted.

## Tests
- Reducer: scripted event sequence (incl. exec_error → repair → success → feedback → approved) yields expected canvas states.
- Counter never exceeds 12; terminal states mutually exclusive.
- Snapshot of SVG for each state at 2 viewports.

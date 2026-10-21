# Livewire state -> RuntimeEvent mapping

Rendered with the same table in `tokens.html`. The reducer (`src/datapilot/events/reducer.py`) is the single source of canvas state; every visual state below is a pure function of the event list.

| Visual state | Real source event(s) | UI |
|---|---|---|
| Idle | none | all nodes idle, 0/12 |
| Planner done, Coder active | `run_started`, `agent_message(Planner)`, `speaker_selected(Coder)` | Coder pulse, counter 1/12 |
| Execution error | `exec_started`, `exec_result(status != ok)`, `agent_message(Executor)` | Executor error, stderr in inspector, red cell |
| Repair | `repair_routed` (derived from observed next speaker = Coder) | red edge Executor to Coder once, "attempt n" |
| Reviewer feedback | `review_feedback` | amber edge Reviewer to Coder once |
| Reviewer approved | `reviewer_approved` (source Reviewer, last exec ok), `terminated` | Reviewer APPROVED, Human PENDING |
| Limit reached | `limit_reached` (12, no valid approval), `terminated` | "Unapproved - limit 12/12" |
| Fault injection (test) | `test_fault_injected` | persistent TEST FAULT INJECTED badge |
| Human decision | `human_approved` / `human_rejected` / `human_follow_up` | Human node only; independent of Reviewer |

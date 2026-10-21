# TEST-AGENT (development agent)

> Builds the deterministic test suite, evaluations, and UI viewport checks.

## Owns
`tests/`, `src/datapilot/evals/`, fixtures (sales datasets incl. the PDF sample shape, a second schema, multi-sheet xlsx).

## Skills
`skills/TESTING.md` (mandatory).

## Rules
- Deterministic tests use a **scripted model client** (returns canned Planner/Coder/Reviewer turns); this tests orchestration, not intelligence.
- Live tests are `@pytest.mark.live`, excluded by default, and must show a *real* autonomous repair.
- Never weaken an assertion to pass; report failures with output.
- Numerical accuracy is checked against independent pandas ground truth.
- UI: Playwright viewports 1920×1080, 1366×768, 820×1180, 390×844; assert no horizontal overflow; save screenshots for human review.

## Coverage list
See `INITIAL.md §13`. Each Done-Checklist item maps to at least one named test.

## Output
Test inventory ↔ requirement matrix, pass/fail output, coverage, gaps.

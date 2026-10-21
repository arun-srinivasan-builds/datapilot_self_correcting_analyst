"""Design-preview scenarios and fixture-backed numbers.

NOTHING here is live AI execution. Preview scenarios are *scripted* event sequences that exercise
the real event model and reducer so the Livewire can be reviewed before M3. Every scenario is
labelled "design preview" in the UI, and token usage is never invented (it is simply absent).
Analytical numbers are computed with pandas from fixtures/sales_sample.csv, not produced by agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from datapilot.events import EventStore, EventType, RuntimeEvent

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "fixtures" / "sales_sample.csv"
HARNESS = "test_harness (design preview)"
PREVIEW_SOURCE = "design_preview"

PLAN = (
    "1) revenue = units × unit_price × (1 − discount)  2) group by month + category "
    "(Aug vs Sep)  3) biggest drop  4) split by region  5) 2 charts"
)
CODE_V1 = """import pandas as pd, json
import matplotlib; matplotlib.use("Agg")
df = pd.read_csv(DATA_PATH, parse_dates=["order_date"])
df["month"] = df["order_date"].dt.to_period("M")
rev = df.groupby(["month", "category"])["revenue"].sum().unstack()
change = (rev.loc["2026-09"] - rev.loc["2026-08"]).sort_values()"""
ERR_V1 = """Traceback (most recent call last):
  File "analysis.py", line 5, in <module>
    rev = df.groupby(["month", "category"])["revenue"].sum().unstack()
KeyError: 'Column not found: revenue'
exit_code=1"""
CODE_V2 = """# Coder revision 2 - derived the missing revenue column
import pandas as pd, json
import matplotlib; matplotlib.use("Agg")
df = pd.read_csv(DATA_PATH, parse_dates=["order_date"])
df["revenue"] = df.units * df.unit_price * (1 - df.discount)
df["month"] = df["order_date"].dt.to_period("M")
rev = df.groupby(["month", "category"])["revenue"].sum().unstack()"""
CODE_FAULT = """# Coder output AFTER test-harness mutation (column 'units' renamed to 'qty')
df = pd.read_csv(DATA_PATH, parse_dates=["order_date"])
df["revenue"] = df.qty * df.unit_price * (1 - df.discount)"""
ERR_FAULT = """Traceback (most recent call last):
  File "analysis.py", line 4, in <module>
    df["revenue"] = df.units * df.unit_price * (1 - df.discount)
AttributeError: 'DataFrame' object has no attribute 'units'
exit_code=1"""
REVIEW_FB = (
    '1. Chart 2 has no y-axis label or unit - add "Revenue change (₹ million)".\n'
    "2. State that South's decline is partly offset by growth in the other regions.\n"
    "Executor output matches results.json; numbers verified."
)
APPROVAL = (
    "Verified: figures in stdout match results.json; both charts have title, axis labels "
    "and units; answer addresses category and region.\nAPPROVED"
)

Spec = tuple[EventType, str, dict[str, Any]]


def _msg(agent: str, event: str, outcome: str, tone: str = "") -> Spec:
    return (
        EventType.AGENT_MESSAGE,
        agent,
        {"event": event, "outcome": outcome, "tone": tone, "preview": True},
    )


def _code(version: int, text: str, mark: tuple[int, str] | None = None) -> Spec:
    return (
        EventType.CODE_GENERATED,
        "Coder",
        {
            "version": version,
            "code": text,
            "mark_line": mark[0] if mark else 0,
            "mark_kind": mark[1] if mark else "",
        },
    )


def _exec_err(stderr: str) -> list[Spec]:
    return [
        (EventType.EXEC_STARTED, "Executor", {"preview": True}),
        (
            EventType.EXEC_RESULT,
            "Executor",
            {"status": "error", "exit_code": 1, "stderr": stderr, "stdout": ""},
        ),
        _msg("Executor", "exec_result", "error · exit 1", "bad"),
    ]


def _exec_ok(note: str) -> list[Spec]:
    return [
        (EventType.EXEC_STARTED, "Executor", {"preview": True}),
        (
            EventType.EXEC_RESULT,
            "Executor",
            {"status": "ok", "exit_code": 0, "stderr": "", "stdout": note},
        ),
        _msg("Executor", "exec_result", f"ok · exit 0 · {note}".rstrip(" ·"), "ok"),
    ]


START: Spec = (
    EventType.RUN_STARTED,
    "app",
    {
        "question": "Which category had the biggest revenue drop in September vs August, "
        "and which region caused most of it?",
        "mode": "guarded_selector",
        "preview": True,
    },
)
PLAN_MSG = _msg(
    "Planner", "agent_message", "Plan: 5 steps (revenue, group, compare, split, charts)"
)
PLAN_EVT: Spec = (
    EventType.AGENT_MESSAGE,
    "Planner",
    {
        "event": "agent_message",
        "outcome": "Plan: 5 steps (revenue, group, compare, split, charts)",
        "tone": "",
        "plan": PLAN,
        "preview": True,
    },
)
SEL_CODER: Spec = (EventType.SPEAKER_SELECTED, PREVIEW_SOURCE, {"next": "Coder"})
REPAIR: Spec = (EventType.REPAIR_ROUTED, PREVIEW_SOURCE, {"attempt": 1})


def _through_first_error() -> list[Spec]:
    return [
        START,
        PLAN_EVT,
        _code(1, CODE_V1, (5, "hl")),
        _msg("Coder", "code_generated", "analysis.py v1 · 23 lines"),
        *_exec_err(ERR_V1),
    ]


def _through_feedback() -> list[Spec]:
    return [
        *_through_first_error(),
        REPAIR,
        _code(2, CODE_V2, (5, "add")),
        _msg("Coder", "code_generated", "analysis.py v2 · derives revenue column"),
        *_exec_ok("2 charts + results.json"),
        (EventType.REVIEW_FEEDBACK, "Reviewer", {"text": REVIEW_FB, "issues": 2}),
        _msg("Reviewer", "review_feedback", "2 issues: axis unit, offset note", "warn"),
        SEL_CODER,
    ]


def _approved() -> list[Spec]:
    return [
        *_through_feedback()[:-1],
        _code(3, CODE_V2, (5, "add")),
        _msg("Coder", "code_generated", "analysis.py v3 · labels + note"),
        *_exec_ok(""),
        _msg("Reviewer", "reviewer_approved", "APPROVED", "ok"),
        (EventType.REVIEWER_APPROVED, "Reviewer", {"text": APPROVAL, "message": 9}),
        (EventType.TERMINATED, PREVIEW_SOURCE, {"reason": "REVIEWER_APPROVED"}),
    ]


def _limit() -> list[Spec]:
    seq: list[Spec] = [START, PLAN_EVT]
    for ver, err in ((1, True), (2, True), (3, False)):
        seq += [
            _code(ver, CODE_V1, (5, "hl")),
            _msg("Coder", "code_generated", f"analysis.py v{ver}"),
        ]
        seq += _exec_err(ERR_V1) if err else _exec_ok("results.json")
    seq += [
        (EventType.REVIEW_FEEDBACK, "Reviewer", {"text": REVIEW_FB, "issues": 3}),
        _msg("Reviewer", "review_feedback", "3 issues", "warn"),
    ]
    seq += [
        _code(4, CODE_V1, (5, "hl")),
        _msg("Coder", "code_generated", "analysis.py v4"),
        *_exec_err(ERR_V1),
    ]
    seq += [
        _code(5, CODE_V2, (5, "add")),
        _msg("Coder", "code_generated", "analysis.py v5"),
        *_exec_ok("not reviewed"),
    ]
    seq += [
        (EventType.LIMIT_REACHED, PREVIEW_SOURCE, {"count": 12}),
        (EventType.TERMINATED, PREVIEW_SOURCE, {"reason": "LIMIT_REACHED"}),
    ]
    return seq


SCENARIOS: dict[str, tuple[str, list[Spec]]] = {
    "running": (
        "Running",
        [START, PLAN_EVT, (EventType.SPEAKER_SELECTED, PREVIEW_SOURCE, {"next": "Coder"})],
    ),
    "exec-error": ("Execution error", _through_first_error()),
    "repair": ("Repair", [*_through_first_error(), REPAIR, SEL_CODER]),
    "reviewer-feedback": ("Reviewer feedback", _through_feedback()),
    "approved": ("Reviewer approved", _approved()),
    "limit-reached": ("Limit reached", _limit()),
    "fault-injection": (
        "Fault injection (test)",
        [
            START,
            PLAN_EVT,
            (
                EventType.TEST_FAULT_INJECTED,
                HARNESS,
                {"kind": "rename_column", "detail": "'units' renamed to 'qty' in Coder output"},
            ),
            _code(1, CODE_FAULT, (3, "del")),
            _msg("Coder", "code_generated", "v1 · mutated by test harness (TEST FAULT)", "warn"),
            *_exec_err(ERR_FAULT),
            REPAIR,
            SEL_CODER,
        ],
    ),
}
SCENARIO_ORDER = list(SCENARIOS)


def events_for(key: str | None, human: str | None = None) -> tuple[RuntimeEvent, ...]:
    """Build the event list for a preview scenario (plus an optional real human decision)."""
    store = EventStore(f"preview-{key or 'none'}")
    if key and key in SCENARIOS:
        for etype, source, payload in SCENARIOS[key][1]:
            store.append(etype, source, {**payload, "preview": True})
        # a human decision can never make a run that the Reviewer did not approve "approved"
        if human == "approved" and key != "approved":
            human = None
        if human:
            kind = {
                "approved": EventType.HUMAN_APPROVED,
                "rejected": EventType.HUMAN_REJECTED,
                "follow_up": EventType.HUMAN_FOLLOW_UP,
            }[human]
            store.append(kind, "human", {"preview": True})
    return store.snapshot()


# --------------------------------------------------------------------------- fixture analysis
@dataclass(frozen=True)
class PreviewAnalysis:
    category_change: tuple[tuple[str, float], ...]  # ascending (biggest drop first)
    region_change: tuple[tuple[str, float], ...]
    monthly: tuple[tuple[str, float], ...]
    category_aug: dict[str, float]
    category_sep: dict[str, float]
    top_category: str
    top_region: str
    aug_total: float
    sep_total: float
    offset: float
    rows: int


def fixture_analysis(path: Path = FIXTURE) -> PreviewAnalysis | None:
    """Real pandas numbers from the sample fixture (labelled design preview in the UI)."""
    if not path.is_file():
        return None
    df = pd.read_csv(path)
    df["revenue"] = df["units"] * df["unit_price"] * (1 - df["discount"])
    df["month"] = df["order_date"].str[:7]
    cat = df.pivot_table(index="category", columns="month", values="revenue", aggfunc="sum")
    change = (cat["2026-09"] - cat["2026-08"]).sort_values()
    top_cat = str(change.index[0])
    sub = df[(df["category"] == top_cat) & df["month"].isin(["2026-08", "2026-09"])]
    reg = sub.pivot_table(index="region", columns="month", values="revenue", aggfunc="sum")
    reg_change = (reg["2026-09"] - reg["2026-08"]).sort_values()
    monthly = df.groupby("month")["revenue"].sum()
    return PreviewAnalysis(
        category_change=tuple((str(k), float(v)) for k, v in change.items()),
        region_change=tuple((str(k), float(v)) for k, v in reg_change.items()),
        monthly=tuple((str(k), float(v)) for k, v in monthly.items()),
        category_aug={str(k): float(v) for k, v in cat["2026-08"].items()},
        category_sep={str(k): float(v) for k, v in cat["2026-09"].items()},
        top_category=top_cat,
        top_region=str(reg_change.index[0]),
        aug_total=float(cat["2026-08"].sum()),
        sep_total=float(cat["2026-09"].sum()),
        offset=float(reg_change.iloc[1:].sum()),
        rows=len(df),
    )

"""Stage 5 harness: scripted model replies + the REAL AutoGen teams + the REAL broker/containers.

Only the LLM is scripted (deterministic replay). Execution results are never simulated: every
`ExecutionResult` comes from a real container, and a spy records them so tests can prove that every
event in the EventStore corresponds to a genuine execution.
"""

from __future__ import annotations

import faulthandler
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from datapilot.agents.participants import RoleClients
from datapilot.agents.runner import RunConfig, RunControl, run_question
from datapilot.agents.teams import Mode
from datapilot.agents.termination import RunOutcome
from datapilot.events import CanvasState, EventStore, RuntimeEvent, reduce_events
from datapilot.ingestion.loader import load_dataset
from datapilot.ingestion.profile import profile_frame, sample_rows
from datapilot.sandbox.backend import BrokerBackend
from datapilot.sandbox.client import BrokerClient
from datapilot.sandbox.contracts import ExecutionResult
from tests.agents.helpers import client
from tests.sandbox.conftest import Api

ROOT = Path(__file__).resolve().parents[2]
SALES = ROOT / "fixtures" / "sales_sample.csv"
TRUTH = json.loads((ROOT / "fixtures" / "sales_sample.truth.json").read_text(encoding="utf-8"))
EVIDENCE = ROOT / "docs" / "evidence" / "m3" / "stage5"
QUESTION = "Which category had the biggest revenue drop in September vs August, and which region?"
PLAN = "1) revenue = units x unit_price x (1 - discount)\n2) group by month and category\n3) compare Aug vs Sep\n4) split the worst category by region\n5) one chart"

FENCE = "```"


def block(code: str, intro: str = "Here is the script:") -> str:
    return f"{intro}\n{FENCE}python\n{code}\n{FENCE}"


GOOD = """import json, os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

df = pd.read_csv(os.environ["DATA_PATH"], parse_dates=["order_date"])
df["revenue"] = df["units"] * df["unit_price"] * (1 - df["discount"])
df["month"] = df["order_date"].dt.strftime("%Y-%m")
by_cat = df.pivot_table(index="category", columns="month", values="revenue", aggfunc="sum")
change = (by_cat["2026-09"] - by_cat["2026-08"]).sort_values()
cat = change.index[0]
by_reg = df[df["category"] == cat].pivot_table(
    index="region", columns="month", values="revenue", aggfunc="sum"
)
reg = (by_reg["2026-09"] - by_reg["2026-08"]).sort_values()
print(f"biggest_drop_category={cat} change={change.iloc[0]:.2f}")
print(f"worst_region={reg.index[0]} change={reg.iloc[0]:.2f}")
fig, ax = plt.subplots()
change.plot.barh(ax=ax, title="Revenue change, Aug to Sep, by category")
ax.set_xlabel("Revenue change (INR)")
ax.set_ylabel("Category")
fig.savefig(os.environ["OUTPUT_DIR"] + "/category_change.png", metadata={"Software": None})
facts = [
    {"label": "biggest_drop_category", "value": str(cat), "unit": ""},
    {"label": "biggest_drop_amount", "value": round(float(change.iloc[0]), 2), "unit": "INR"},
    {"label": "worst_region", "value": str(reg.index[0]), "unit": ""},
    {"label": "worst_region_change", "value": round(float(reg.iloc[0]), 2), "unit": "INR"},
]
charts = [{"file": "category_change.png", "title": "Revenue change, Aug to Sep, by category",
           "x_label": "Revenue change (INR)", "y_label": "Category", "unit": "INR"}]
json.dump({"answer_facts": facts, "charts": charts}, open(os.environ["OUTPUT_DIR"] + "/results.json", "w"))
"""
GOOD_V2 = GOOD.replace(
    'print(f"worst_region=', 'print("(revision 2: unit added to labels)")\nprint(f"worst_region='
)
# a natural, genuine Python error (the scripted Coder "forgot" to derive the revenue column)
BAD_KEYERROR = GOOD.replace(
    'df["revenue"] = df["units"] * df["unit_price"] * (1 - df["discount"])\n',
    'print(df["revenue"].sum())\n',
)
NO_RESULTS = 'import os, pandas as pd\ndf = pd.read_csv(os.environ["DATA_PATH"])\nprint(len(df))'
NAN_RESULTS = (
    "import os\nopen(os.environ['OUTPUT_DIR'] + '/results.json', 'w').write("
    '\'{"answer_facts": [{"label": "x", "value": NaN, "unit": ""}]}\')'
)
OOM = "blocks = []\nwhile True:\n    blocks.append(b'x' * (50 * 1024 * 1024))"
SPIN = "while True:\n    pass"
APPROVE = "The figures in the output match results.json and the chart is labelled.\nAPPROVED"
FEEDBACK = "1. State the unit (INR) in the chart title.\n2. Mention the comparison period."


@dataclass
class SpyBackend:
    """Wraps the real BrokerBackend and records every genuine result it returns."""

    inner: BrokerBackend
    results: list[ExecutionResult] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)

    async def run(self, code: str, *, run_id: str) -> ExecutionResult:
        self.codes.append(code)
        result = await self.inner.run(code, run_id=run_id)
        self.results.append(result)
        return result


@dataclass
class RealRun:
    outcome: RunOutcome
    store: EventStore
    clients: RoleClients
    selector: Any
    backend: SpyBackend
    containers_created: list[str]
    fault: Any = None

    @property
    def events(self) -> tuple[RuntimeEvent, ...]:
        return self.store.snapshot()

    @property
    def canvas(self) -> CanvasState:
        return reduce_events(self.events)

    def of(self, type_: str) -> list[RuntimeEvent]:
        return [e for e in self.events if e.type.value == type_]

    @property
    def letters(self) -> str:
        initial = {"Planner": "P", "Coder": "C", "Executor": "E", "Reviewer": "R"}
        return "".join(initial[e.source] for e in self.of("agent_message"))

    def coder_inputs(self) -> list[str]:
        return [_flatten(call["messages"]) for call in self.clients.coder.create_calls]


def _flatten(messages: Any) -> str:
    return "\n".join(str(getattr(m, "content", "")) for m in messages)


def sales_profile(path: Path = SALES) -> dict[str, Any]:
    dataset = load_dataset(path)
    return profile_frame(dataset.frame).to_prompt_dict(sample_rows(dataset.frame))


async def run_real(
    api: Api,
    monkeypatch: Any,
    *,
    coder: list[str],
    reviewer: list[str],
    mode: Mode = "selector",
    planner: list[str] | None = None,
    dataset_path: Path = SALES,
    profile: dict[str, Any] | None = None,
    max_messages: int = 12,
    max_tokens: int = 10_000_000,
    timeout_seconds: int = 120,
    exec_timeout_s: int = 60,
    control: RunControl | None = None,
    selector_replies: list[str] | None = None,
    completion_ceiling: int | None = None,
    name: str | None = None,
    fault: Any = None,
    stage: str = "stage5",
) -> RealRun:
    created: list[str] = []
    _arm_stall_dump(api)
    runtime = api.manager.runtime
    real_create = runtime.create

    def counting_create(spec: Any) -> None:
        created.append(spec.name)
        real_create(spec)

    monkeypatch.setattr(runtime, "create", counting_create)
    kind = "xlsx" if dataset_path.suffix.lower() == ".xlsx" else "csv"
    backend = SpyBackend(
        BrokerBackend(
            BrokerClient(f"http://127.0.0.1:{api.server.port}", api.token),
            dataset_path.read_bytes(),
            kind,
            timeout_s=exec_timeout_s,
        )
    )
    clients = RoleClients(
        planner=client(planner or [PLAN] * 8),
        coder=client(coder),
        reviewer=client(reviewer),
    )
    selector = client(selector_replies or [])
    store = EventStore(f"stage5-{name or 'run'}")
    outcome = await run_question(
        question=QUESTION,
        profile=profile or sales_profile(dataset_path),
        config=RunConfig(
            mode,
            max_messages,
            max_tokens,
            timeout_seconds,
            require_results=True,
            completion_ceiling=completion_ceiling,
            fault=fault,
        ),
        clients=clients,
        selector_client=selector,
        backend=backend,
        store=store,
        control=control,
    )
    faulthandler.cancel_dump_traceback_later()  # the scenario finished: nothing stalled
    run = RealRun(outcome, store, clients, selector, backend, created, fault)
    # artifacts of finished executions are released (the broker also expires them by age)
    for result in backend.results:
        await backend.inner.release(result)
    if name:
        write_evidence(name, run, EVIDENCE.parent / stage)
    return run


def _plain(value: Any) -> Any:
    """json default: frozen event payloads (MappingProxyType / tuples) -> plain containers."""
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, tuple | set | frozenset):
        return list(value)
    raise TypeError(f"not serializable: {type(value).__name__}")


def sha12(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()[:12]


def assert_matches_truth(results_text: str) -> None:
    facts = {f["label"]: f["value"] for f in json.loads(results_text)["answer_facts"]}
    assert facts["biggest_drop_category"] == TRUTH["biggest_drop_category"]
    assert abs(facts["biggest_drop_amount"] - TRUTH["biggest_drop_amount"]) < 0.02
    worst = min(TRUTH["region_change_for_that_category"].items(), key=lambda kv: kv[1])
    assert facts["worst_region"] == worst[0]
    assert abs(facts["worst_region_change"] - worst[1]) < 0.02


def write_evidence(name: str, run: RealRun, root: Path = EVIDENCE) -> None:
    """Persist the actual event log and a compact summary of this scripted-LLM/real-sandbox run."""
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    run.store.dump_jsonl(folder / "events.jsonl")
    state = run.canvas
    summary = {
        "scenario": name,
        "llm": "scripted replay (no live model calls)",
        "sandbox": "real Docker containers via the real broker",
        "outcome": run.outcome.value,
        "speaker_order": run.letters,
        "agent_messages": state.message_count,
        "phase": state.phase,
        "repair_attempts": state.repair_attempts,
        "feedback_rounds": state.feedback_rounds,
        "reviewer_verified": state.reviewer_verified,
        "human": state.human,
        "containers_created": len(run.containers_created),
        "executions": [
            {
                "status": r.status,
                "exit_code": r.exit_code,
                "duration_ms": r.duration_ms,
                "stderr_head": r.stderr.strip().splitlines()[-1][:160] if r.stderr.strip() else "",
                "artifacts": [a.name for a in r.artifacts],
            }
            for r in run.backend.results
        ],
        "code_hashes": [sha12(c) for c in run.backend.codes],
        "usage": run.of("terminated")[0].payload["usage_by_source"] if run.of("terminated") else {},
        "total_tokens": state.input_tokens + state.output_tokens,
        "event_types": [e.type.value for e in run.events],
    }
    (folder / "summary.json").write_text(
        json.dumps(summary, indent=2, default=_plain), encoding="utf-8"
    )


def explain(run: RealRun) -> str:
    """Failure message helper: why did the run end the way it did?"""
    err = [dict(e.payload) for e in run.of("run_error")]
    term = [dict(e.payload) for e in run.of("terminated")]
    return f"outcome={run.outcome.value} letters={run.letters} run_error={err} terminated={term}"


def write_fault_record(name: str, run: RealRun) -> dict[str, Any]:
    """Audit file for an injected scenario: original, executed and corrected code + identifiers."""
    folder = EVIDENCE.parent / "stage6" / name
    folder.mkdir(parents=True, exist_ok=True)
    events = run.events
    injected = [e for e in events if e.type.value == "test_fault_injected"]
    execs = []
    for result, code, started, finished in zip(
        run.backend.results,
        run.backend.codes,
        run.of("exec_started"),
        run.of("exec_result"),
        strict=False,
    ):
        execs.append(
            {
                "broker_exec_id": result.exec_id,
                "code_hash": sha12(code),
                "injected_fault": finished.payload.get("injected_fault"),
                "status": result.status,
                "exit_code": result.exit_code,
                "stderr_tail": "\n".join(result.stderr.strip().splitlines()[-3:]),
                "duration_ms": result.duration_ms,
                "exec_started_seq": started.seq,
                "exec_result_seq": finished.seq,
            }
        )
    record = {
        "scenario": name,
        "fault": run.fault.summary() if run.fault else None,
        "fault_event_seqs": [e.seq for e in injected],
        "executions": execs,
        "outcome": run.outcome.value,
    }
    (folder / "fault-record.json").write_text(
        json.dumps(record, indent=2, default=_plain), encoding="utf-8"
    )
    if run.fault and run.fault.records:
        first = run.fault.records[0]
        (folder / "1-original-coder-output.py").write_text(first.original_code, encoding="utf-8")
        (folder / "2-executed-after-injection.py").write_text(first.mutated_code, encoding="utf-8")
        (folder / "injection.diff").write_text(first.diff + "\n", encoding="utf-8")
    ok = [c for c, r in zip(run.backend.codes, run.backend.results, strict=False) if r.ok]
    if ok:
        (folder / "3-corrected-and-executed.py").write_text(ok[-1], encoding="utf-8")
    return record


STALL_DUMP_AFTER_S = 45
_STALL_FILE = EVIDENCE.parent / "stall-diagnostics.txt"


def _arm_stall_dump(api: Api) -> None:
    """If a scenario runs longer than 45 s, dump every thread's stack (broker handler threads
    included) and the broker's per-phase timings. Cancelled again when the scenario completes."""
    _STALL_FILE.parent.mkdir(parents=True, exist_ok=True)
    handle = _STALL_FILE.open("a", encoding="utf-8")
    handle.write(f"\n=== armed; timing_log so far: {list(api.manager.timing_log)[-3:]} ===\n")
    handle.flush()
    faulthandler.dump_traceback_later(STALL_DUMP_AFTER_S, repeat=False, file=handle)

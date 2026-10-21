"""Session: one dataset, many independent runs, and the separate human-approval stage (M3 Stage 7).

Rules enforced here
- Every question (first or follow-up) is a NEW run: new run_id, new EventStore, new team and
  RunState (fresh 12-message counter, token budget and wall-clock timer).
- The dataset is fixed for the session. Only *Reviewer-approved, contract-valid* results of earlier
  runs are carried forward, and only as sanitized facts + artifact identities (never code, stdout,
  stderr, agent messages or instructions). Failed, limited, timed-out, stopped, errored or
  human-rejected runs are never context.
- Reviewer APPROVED is an agent decision. Human approval is a separate explicit call, refused unless
  the run was Reviewer-approved, is not already decided, the caller presents the artifact digest of
  THAT run, and the artifacts still exist unchanged in the sandbox store. Nothing here ever approves
  automatically, and no user identity is invented.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autogen_core.models import ChatCompletionClient

from datapilot.agents.participants import RoleClients
from datapilot.agents.runner import RunConfig, RunControl, run_to_report
from datapilot.agents.termination import RunOutcome
from datapilot.events import EventStore, EventType, reduce_events
from datapilot.ingestion.loader import load_dataset
from datapilot.ingestion.profile import profile_frame, sample_rows
from datapilot.sandbox.backend import BrokerBackend
from datapilot.sandbox.client import BrokerClient
from datapilot.sandbox.contracts import ExecutionBackend, SandboxUnavailableError

log = logging.getLogger(__name__)
HUMAN_SOURCE = "human"
MAX_CONTEXT_RUNS = 3
MAX_CONTEXT_FACTS = 50
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


class ApprovalRefused(RuntimeError):
    """A human decision was refused. `code` is stable; nothing was recorded as a decision."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class SessionBusy(RuntimeError):
    """A run is still active in this session."""


def _clean(text: str, limit: int) -> str:
    return _CONTROL.sub(" ", text).strip()[:limit]


@dataclass(frozen=True, slots=True)
class Actor:
    """Who took a human decision. Never invented: unidentified unless the caller says otherwise."""

    kind: str = "local_operator"
    identifier: str | None = None  # as supplied by the caller; NOT authenticated here
    verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "identifier": self.identifier, "verified": self.verified}


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    name: str
    size: int
    sha256: str
    exec_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "size": self.size,
            "sha256": self.sha256,
            "exec_id": self.exec_id,
        }


def artifact_digest(run_id: str, artifacts: tuple[ArtifactRef, ...]) -> str:
    """Identity of exactly this run's approved artifact set."""
    lines = [run_id] + sorted(f"{a.name}:{a.sha256}:{a.exec_id}" for a in artifacts)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DatasetRef:
    path: Path
    name: str
    kind: str
    sheet: str | None
    data: bytes = field(repr=False)
    sha256: str
    profile: dict[str, Any] = field(repr=False)

    @classmethod
    def from_path(cls, path: Path, sheet: str | None = None) -> DatasetRef:
        dataset = load_dataset(path, sheet)  # validation + profile happen once, up front
        data = Path(path).read_bytes()
        kind = "xlsx" if Path(path).suffix.lower() in (".xlsx", ".xlsm") else "csv"
        profile = profile_frame(dataset.frame).to_prompt_dict(sample_rows(dataset.frame))
        return cls(
            Path(path), dataset.name, kind, dataset.sheet, data,
            hashlib.sha256(data).hexdigest(), profile,
        )  # fmt: skip


@dataclass(frozen=True, slots=True)
class HumanRecord:
    run_id: str
    decision: str  # approved | rejected
    at: str
    actor: Actor
    reason: str
    artifact_digest: str
    artifacts: tuple[ArtifactRef, ...]
    code_hash: str
    results_sha256: str | None
    session_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "decision": self.decision,
            "at": self.at,
            "actor": self.actor.to_dict(),
            "reason": self.reason,
            "artifact_digest": self.artifact_digest,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "code_hash": self.code_hash,
            "results_sha256": self.results_sha256,
        }


@dataclass
class RunRecord:
    """Everything about one run, kept separate from every other run."""

    run_id: str
    sequence: int
    question: str
    outcome: RunOutcome
    reviewer_approved: bool
    started_at: str
    finished_at: str
    parent_run_id: str | None
    context_run_ids: tuple[str, ...]
    messages: int
    input_tokens: int
    output_tokens: int
    usage_by_source: dict[str, dict[str, int]]
    exec_ids: tuple[str, ...]
    code_hashes: tuple[str, ...]
    facts: tuple[dict[str, Any], ...] = ()
    artifacts: tuple[ArtifactRef, ...] = ()
    code_hash: str = ""
    results_sha256: str | None = None
    human: HumanRecord | None = None

    @property
    def human_status(self) -> str:
        return self.human.decision if self.human else "none"

    @property
    def trusted(self) -> bool:
        """May feed later runs: Reviewer-approved and not rejected by a human."""
        return self.reviewer_approved and self.human_status != "rejected"

    @property
    def digest(self) -> str:
        return artifact_digest(self.run_id, self.artifacts)


class Session:
    def __init__(
        self,
        dataset: DatasetRef,
        broker: BrokerClient,
        *,
        exec_timeout_s: int = 60,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.session_id = secrets.token_hex(4)
        self.dataset = dataset
        self._broker = broker
        self._exec_timeout = exec_timeout_s
        self._clock = clock
        self._runs: dict[str, RunRecord] = {}
        self._order: list[str] = []
        self._stores: dict[str, EventStore] = {}
        self._active: str | None = None
        self._lock = asyncio.Lock()
        self.attempts: list[dict[str, Any]] = []  # every human-decision attempt, incl. refusals

    # ------------------------------------------------------------------ accessors ------------
    def run(self, run_id: str) -> RunRecord:
        try:
            return self._runs[run_id]
        except KeyError:
            raise ApprovalRefused("unknown_run", f"no run '{run_id}' in this session") from None

    def store(self, run_id: str) -> EventStore:
        return self._stores[run_id]

    @property
    def runs(self) -> tuple[RunRecord, ...]:
        return tuple(self._runs[r] for r in self._order)

    def make_backend(self, *, timeout_s: int | None = None) -> BrokerBackend:
        """The session's dataset is fixed: every run executes against exactly these bytes."""
        return BrokerBackend(
            self._broker, self.dataset.data, self.dataset.kind,
            sheet=self.dataset.sheet, timeout_s=timeout_s or self._exec_timeout,
        )  # fmt: skip

    # ------------------------------------------------------------------ context --------------
    def context_for_next_run(self) -> tuple[dict[str, Any], ...]:
        """Sanitized, verified facts of earlier trusted runs. Nothing else is ever carried over."""
        trusted = [r for r in self.runs if r.trusted][-MAX_CONTEXT_RUNS:]
        return tuple(self._context_entry(r) for r in trusted)

    @staticmethod
    def _context_entry(record: RunRecord) -> dict[str, Any]:
        status = "reviewer_approved" + (
            "+human_approved" if record.human_status == "approved" else ""
        )
        return {
            "run_id": record.run_id,
            "question": _clean(record.question, 300),
            "status": status,
            "facts": [
                {"label": f["label"], "value": f["value"], "unit": f["unit"]}
                for f in record.facts[:MAX_CONTEXT_FACTS]
            ],
            "artifacts": [{"name": a.name, "sha256": a.sha256} for a in record.artifacts],
        }

    # ------------------------------------------------------------------ runs -----------------
    async def ask(
        self,
        question: str,
        *,
        clients: RoleClients,
        selector_client: ChatCompletionClient,
        config: RunConfig,
        control: RunControl | None = None,
        parent_run_id: str | None = None,
        wrap_backend: Callable[[BrokerBackend], ExecutionBackend] | None = None,
    ) -> RunRecord:
        """Run one question as a brand-new run (first question or follow-up)."""
        if self._active is not None:
            raise SessionBusy(f"run {self._active} is still active")
        if parent_run_id is not None:
            self.run(parent_run_id)  # must be a run of this session
        sequence = len(self._order) + 1
        run_id = f"s{self.session_id}-r{sequence}"
        store = EventStore(run_id)
        self._stores[run_id] = store
        self._active = run_id
        context = self.context_for_next_run()
        started = self._clock()
        backend = self.make_backend()
        try:
            report = await run_to_report(
                question=question,
                profile=self.dataset.profile,
                config=config,  # a fresh RunState/timer is created inside; budgets reset per run
                clients=clients,
                selector_client=selector_client,
                backend=wrap_backend(backend) if wrap_backend else backend,
                store=store,
                context=context,
                control=control,
                run_meta={
                    "session_id": self.session_id,
                    "sequence": sequence,
                    "parent_run_id": parent_run_id,
                    "context_run_ids": [c["run_id"] for c in context],
                    "dataset_sha256": self.dataset.sha256,
                },
            )
        finally:
            self._active = None
        record = self._record(
            run_id, sequence, question, report, store, started, parent_run_id, context
        )
        self._runs[run_id] = record
        self._order.append(run_id)
        if parent_run_id is not None:
            store_parent = self._stores[parent_run_id]
            store_parent.append(
                EventType.HUMAN_FOLLOW_UP, HUMAN_SOURCE, {"child_run_id": run_id, "at": self._now()}
            )
        return record

    def _record(
        self, run_id: str, sequence: int, question: str, report: Any, store: EventStore,
        started: datetime, parent_run_id: str | None, context: tuple[dict[str, Any], ...],
    ) -> RunRecord:  # fmt: skip
        state, events = report.state, store.snapshot()
        canvas = reduce_events(events)
        reviewer_ok = (
            report.outcome is RunOutcome.REVIEWER_APPROVED
            and canvas.phase == "approved"
            and canvas.violations == ()
            and state.last_valid_result is not None
        )
        final = state.last_valid_result if reviewer_ok else None
        facts, artifacts, results_sha = (), (), None
        if final is not None:
            facts = _verified_facts(final.results_json)
            artifacts = tuple(
                ArtifactRef(a.name, a.size, a.sha256, final.exec_id) for a in final.artifacts
            )
            if final.results_json is not None:
                results_sha = hashlib.sha256(final.results_json.encode("utf-8")).hexdigest()
        exec_ids = tuple(
            e.payload["exec_id"] for e in events
            if e.type is EventType.EXEC_RESULT and e.payload.get("exec_id")
        )  # fmt: skip
        return RunRecord(
            run_id=run_id,
            sequence=sequence,
            question=question,
            outcome=report.outcome,
            reviewer_approved=reviewer_ok,
            started_at=started.isoformat(timespec="seconds"),
            finished_at=self._now(),
            parent_run_id=parent_run_id,
            context_run_ids=tuple(c["run_id"] for c in context),
            messages=state.agent_messages,
            input_tokens=state.input_tokens,
            output_tokens=state.output_tokens,
            usage_by_source={
                k: {"input_tokens": v[0], "output_tokens": v[1], "calls": v[2]}
                for k, v in state.usage_by_source.items()
            },
            exec_ids=exec_ids,
            code_hashes=tuple(
                e.payload["code_hash"] for e in events if e.type is EventType.EXEC_STARTED
            ),
            facts=facts,
            artifacts=artifacts,
            code_hash=state.last_valid_code_hash if reviewer_ok else "",
            results_sha256=results_sha,
        )

    def _now(self) -> str:
        return self._clock().isoformat(timespec="seconds")

    async def release_run(self, run_id: str) -> None:
        """Drop the sandbox-side artifacts of every execution of this run."""
        for exec_id in self.run(run_id).exec_ids:
            try:
                await self._broker.delete(exec_id)
            except SandboxUnavailableError:
                log.warning("could not release artifacts of %s", exec_id)

    async def release_all(self) -> None:
        for run_id in self._order:
            await self.release_run(run_id)

    # ------------------------------------------------------------------ human stage ----------
    def _refuse(self, kind: str, run_id: str, actor: Actor, code: str, message: str) -> None:
        self.attempts.append(
            {
                "kind": kind,
                "run_id": run_id,
                "at": self._now(),
                "actor": actor.to_dict(),
                "result": "refused",
                "code": code,
            }  # fmt: skip
        )
        raise ApprovalRefused(code, message)

    def _check_decidable(self, kind: str, run_id: str, actor: Actor) -> RunRecord:
        if self._active == run_id:
            self._refuse(kind, run_id, actor, "run_active", "the run has not finished")
        record = self._runs.get(run_id)
        if record is None:
            self._refuse(kind, run_id, actor, "unknown_run", "no such run in this session")
        assert record is not None  # noqa: S101 - _refuse raises
        if record.human is not None:
            self._refuse(
                kind, run_id, actor, "already_decided",
                f"this run already has a human decision ({record.human.decision})",
            )  # fmt: skip
        return record

    async def approve(
        self, run_id: str, *, artifact_digest_seen: str, actor: Actor | None = None
    ) -> HumanRecord:
        """Explicit human approval of exactly the artifacts of `run_id` that the human saw."""
        actor = actor or Actor()
        async with self._lock:
            record = self._check_decidable("approve", run_id, actor)
            if not record.reviewer_approved:
                self._refuse(
                    "approve", run_id, actor, "not_reviewer_approved",
                    f"run ended {record.outcome.value}; only a Reviewer-approved run is approvable",
                )  # fmt: skip
            if artifact_digest_seen != record.digest:
                other = next((r for r in self.runs if r.digest == artifact_digest_seen), None)
                code = "different_run" if other else "stale_digest"
                self._refuse(
                    "approve", run_id, actor, code, "the artifacts presented are not this run's"
                )
            await self._verify_artifacts("approve", record, actor)
            if (
                record.human is not None
            ):  # re-check: another decision may have landed while verifying
                self._refuse("approve", run_id, actor, "already_decided", "decided meanwhile")
            return self._record_decision(record, "approved", "", actor)

    async def _verify_artifacts(self, kind: str, record: RunRecord, actor: Actor) -> None:
        for artifact in record.artifacts:
            try:
                data = await self._broker.artifact(artifact.exec_id, artifact.name)
            except SandboxUnavailableError:
                self._refuse(kind, record.run_id, actor, "stale_artifacts",
                             f"artifact {artifact.name} is no longer available")  # fmt: skip
            if hashlib.sha256(data).hexdigest() != artifact.sha256:
                self._refuse(kind, record.run_id, actor, "stale_artifacts",
                             f"artifact {artifact.name} changed since the run")  # fmt: skip

    def reject(self, run_id: str, *, reason: str = "", actor: Actor | None = None) -> HumanRecord:
        """Explicit human rejection; recorded separately from any Reviewer feedback."""
        actor = actor or Actor()
        record = self._check_decidable("reject", run_id, actor)
        if reduce_events(self._stores[run_id].snapshot()).is_terminal is False:
            self._refuse("reject", run_id, actor, "run_active", "the run has not finished")
        return self._record_decision(record, "rejected", _clean(reason, 500), actor)

    def _record_decision(
        self, record: RunRecord, decision: str, reason: str, actor: Actor
    ) -> HumanRecord:
        human = HumanRecord(
            record.run_id, decision, self._now(), actor, reason, record.digest, record.artifacts,
            record.code_hash, record.results_sha256, self.session_id,
        )  # fmt: skip
        record.human = human
        event = EventType.HUMAN_APPROVED if decision == "approved" else EventType.HUMAN_REJECTED
        self._stores[record.run_id].append(event, HUMAN_SOURCE, human.to_dict())
        self.attempts.append(
            {
                "kind": decision,
                "run_id": record.run_id,
                "at": human.at,
                "actor": actor.to_dict(),
                "result": "recorded",
                "code": "",
            }  # fmt: skip
        )
        return human

    # ------------------------------------------------------------------ audit ----------------
    def audit_log(self) -> list[dict[str, Any]]:
        """Recorded decisions (who/what, run_id, timestamp, artifacts); no identity is invented."""
        return [r.human.to_dict() for r in self.runs if r.human is not None]

    def dump_audit(self, path: Path) -> None:
        payload = {
            "session_id": self.session_id,
            "decisions": self.audit_log(),
            "attempts": self.attempts,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _verified_facts(results_json: str | None) -> tuple[dict[str, Any], ...]:
    """Facts from a contract-valid results.json, sanitized and bounded."""
    if not results_json:
        return ()
    try:
        raw = json.loads(results_json).get("answer_facts", [])
    except (ValueError, AttributeError):
        return ()
    facts: list[dict[str, Any]] = []
    for item in raw[:MAX_CONTEXT_FACTS]:
        value = item.get("value")
        facts.append(
            {
                "label": _clean(str(item.get("label", "")), 80),
                "value": _clean(value, 200) if isinstance(value, str) else value,
                "unit": _clean(str(item.get("unit", "")), 20),
            }
        )
    return tuple(facts)

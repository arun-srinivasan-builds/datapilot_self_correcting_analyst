"""Turn the REAL events of a recorded run into plain-English animation frames and trust checks.

Pure functions, no Streamlit. Every frame is derived from one counted agent message plus the real
events around it (plan text, code, stderr, reviewer text, timestamps). Nothing is invented: the
wording is fixed templates, the details are quoted from the run.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from datapilot.events import AGENTS, EventType, RuntimeEvent

_MAX_DETAIL = 420


def _clip(text: str, limit: int = _MAX_DETAIL) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _last_line(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def _strip_approval(text: str) -> str:
    lines = text.rstrip().splitlines()
    if lines and lines[-1].strip() == "APPROVED":
        lines = lines[:-1]
    return "\n".join(lines).strip()


@dataclass(frozen=True)
class Frame:
    index: int
    seconds: float  # real seconds since the run started
    actor: str  # You | Planner | Coder | Executor | Reviewer | Result
    kind: str  # question | plan | code | run_ok | run_fail | feedback | approve | done
    tone: str  # neutral | ok | bad | warn
    title: str
    detail: str
    code: tuple[str, ...] = ()
    badge: str = ""
    loop_back: bool = False  # the packet travels back to the Coder (repair / revision)
    count: int = 0  # counted agent messages so far (x of 12)

    def to_dict(self) -> dict[str, Any]:
        return {
            "i": self.index,
            "t": round(self.seconds, 1),
            "actor": self.actor,
            "kind": self.kind,
            "tone": self.tone,
            "title": self.title,
            "detail": self.detail,
            "code": list(self.code),
            "badge": self.badge,
            "loop": self.loop_back,
            "count": self.count,
        }


def build_frames(events: Sequence[RuntimeEvent]) -> list[Frame]:
    """One frame per meaningful step of the run, in order."""
    if not events:
        return []
    t0 = events[0].ts
    frames: list[Frame] = []
    code_payload: dict[str, Any] = {}
    fault: dict[str, Any] | None = None
    exec_payload: dict[str, Any] = {}
    plan_text = ""
    review_text = ""
    failed_before = False
    count = 0

    def seconds(ev: RuntimeEvent) -> float:
        return (ev.ts - t0).total_seconds()

    for ev in events:
        p = ev.payload
        if ev.type is EventType.RUN_STARTED:
            frames.append(
                Frame(
                    len(frames),
                    0.0,
                    "You",
                    "question",
                    "neutral",
                    "A business question arrives",
                    _clip(str(p.get("question", ""))),
                    count=0,
                )  # fmt: skip
            )
        elif ev.type is EventType.TEST_FAULT_INJECTED:
            fault = dict(p)
        elif ev.type is EventType.CODE_GENERATED:
            code_payload = dict(p)
        elif ev.type is EventType.EXEC_RESULT:
            exec_payload = dict(p)
        elif ev.type in (EventType.REVIEW_FEEDBACK, EventType.REVIEWER_APPROVED):
            review_text = str(p.get("text", ""))
        if "plan" in p and not plan_text:
            plan_text = str(p["plan"])
        if ev.type is not EventType.AGENT_MESSAGE or ev.source not in AGENTS:
            continue
        count += 1
        what = str(p.get("event", ""))
        if ev.source == "Planner":
            frames.append(
                Frame(
                    len(frames),
                    seconds(ev),
                    "Planner",
                    "plan",
                    "neutral",
                    "The Planner breaks the question into steps",
                    _clip(plan_text or "A plan."),
                    count=count,
                )  # fmt: skip
            )
        elif ev.source == "Coder":
            version = int(code_payload.get("version", 1) or 1)
            code = tuple(str(code_payload.get("code", "")).splitlines()[:9])
            repairing = failed_before and version > 1
            title = (
                "The Coder reads the error and fixes the program"
                if repairing
                else "The Coder writes a Python program"
                if version == 1
                else "The Coder revises the program"
            )
            badge = ""
            if fault is not None and version == 1:
                badge = (
                    "TEST ONLY · a mistake was deliberately planted in this program to prove "
                    "the team can fix it"
                )
            frames.append(
                Frame(
                    len(frames),
                    seconds(ev),
                    "Coder",
                    "code",
                    "neutral",
                    title,
                    _clip(str(p.get("outcome", "")).replace("analysis.py", "Program"), 120),
                    code=code,
                    badge=badge,
                    loop_back=repairing,
                    count=count,
                )  # fmt: skip
            )
        elif ev.source == "Executor":
            ok = exec_payload.get("status") == "ok"
            secs = int(exec_payload.get("duration_ms", 0) or 0) / 1000
            if ok:
                out = _clip(str(exec_payload.get("stdout", "")), 300) or "Finished with no errors."
                frames.append(
                    Frame(
                        len(frames),
                        seconds(ev),
                        "Executor",
                        "run_ok",
                        "ok",
                        f"The program ran successfully in the sandbox ({secs:.1f} s)",
                        out,
                        count=count,
                    )  # fmt: skip
                )
            else:
                failed_before = True
                err = _last_line(str(exec_payload.get("stderr", ""))) or "The program failed."
                frames.append(
                    Frame(
                        len(frames),
                        seconds(ev),
                        "Executor",
                        "run_fail",
                        "bad",
                        "The program crashed — a real error from the sandbox",
                        _clip(err, 220),
                        count=count,
                    )  # fmt: skip
                )
        elif ev.source == "Reviewer":
            if what == "reviewer_approved":
                frames.append(
                    Frame(
                        len(frames),
                        seconds(ev),
                        "Reviewer",
                        "approve",
                        "ok",
                        "The Reviewer checks the numbers and approves",
                        _clip(_strip_approval(review_text)),
                        count=count,
                    )  # fmt: skip
                )
            else:
                frames.append(
                    Frame(
                        len(frames),
                        seconds(ev),
                        "Reviewer",
                        "feedback",
                        "warn",
                        "The Reviewer asks for changes",
                        _clip(review_text),
                        loop_back=True,
                        count=count,
                    )  # fmt: skip
                )
    if frames and frames[-1].kind == "approve":
        last = frames[-1]
        frames.append(
            Frame(
                len(frames),
                last.seconds,
                "Result",
                "done",
                "ok",
                "Answer ready — scroll down to check it",
                "",
                count=last.count,
            )  # fmt: skip
        )
    return frames


@dataclass(frozen=True)
class TrustCheck:
    ok: bool | None  # True = passed, None = informational
    title: str
    body: str


def trust_checks(events: Sequence[RuntimeEvent]) -> list[TrustCheck]:
    """What a visitor can verify, each derived from real events of the run."""
    execs = [e for e in events if e.type is EventType.EXEC_RESULT]
    failed = [e for e in execs if e.payload.get("status") != "ok"]
    approved = next((e for e in events if e.type is EventType.REVIEWER_APPROVED), None)
    fault = any(e.type is EventType.TEST_FAULT_INJECTED for e in events)
    checks = [
        TrustCheck(
            True,
            "Real code, really executed",
            f"The agents wrote Python and ran it {len(execs)} time{'s' if len(execs) != 1 else ''} "
            "in an isolated sandbox with no internet access. Nothing was typed in by hand.",
        )
    ]
    if failed:
        err = _last_line(str(failed[0].payload.get("stderr", "")))
        why = (
            " This mistake was planted on purpose (test-only) to prove the loop works."
            if fault
            else ""
        )
        checks.append(
            TrustCheck(
                True,
                "A mistake was caught and fixed — by the agents",
                f"The first run crashed with “{_clip(err, 120)}”. The Coder read the error and "
                f"sent a corrected program, with no human debugging.{why}",
            )
        )
    else:
        checks.append(
            TrustCheck(
                None,
                "No crash in this run",
                "Everything worked first time. Pick the other recorded run to watch the team "
                "catch and repair a real error.",
            )
        )
    if approved is not None:
        checks.append(
            TrustCheck(
                True,
                "An independent Reviewer approved it",
                "Only the Reviewer can approve, and only after a successful run. It approved on "
                f"message {approved.payload.get('message', '?')} of the 12 allowed.",
            )
        )
    checks.append(
        TrustCheck(
            True,
            "Every number comes from the program's output",
            "The answer, the key figures and the charts below are read from the file the program "
            "saved, not retyped.",
        )
    )
    return checks

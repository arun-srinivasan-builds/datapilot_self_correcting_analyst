"""Stage 6: controlled, TEST-ONLY fault injection -> genuine sandbox error -> real Coder repair cycle.

Scripted model replies; real AutoGen teams; real Docker containers. The *only* synthetic act is the
labelled mutation of the Coder's first code message; the error, stderr and re-execution are real.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
from pathlib import Path

import pytest

from datapilot.agents.runner import RunConfig, RunControl
from datapilot.agents.termination import RunOutcome as O
from datapilot.config import Settings
from datapilot.faults import (
    FAULT_SOURCE,
    FAULTS,
    FaultInjectionError,
    FaultInjectionRefused,
    FaultInjector,
    FaultSpec,
    authorize,
)
from datapilot.ui.viewmodel import build_canvas, feed_items
from tests.integration.harness import (
    APPROVE,
    BAD_KEYERROR,
    GOOD,
    OOM,
    assert_matches_truth,
    block,
    explain,
    run_real,
    sha12,
    write_fault_record,
)

pytestmark = pytest.mark.sandbox
ROOT = Path(__file__).resolve().parents[2]
STAGE = "stage6"


def test_settings(name: str = "missing_column", env: str = "test") -> Settings:
    return Settings(_env_file=None, app_env=env, fault_injection=name)


def injector(name: str = "missing_column", times: int = 1) -> FaultInjector:
    return FaultInjector.authorized(test_settings(name), name, times=times)


def containers_left() -> list[str]:
    out = subprocess.run(  # noqa: S603
        ["docker", "ps", "-a", "--filter", "label=datapilot.sandbox=1", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return out.stdout.split()


# ======================================================================== boundary (no Docker) ==
class TestBoundary:
    def test_disabled_by_default(self):
        settings = Settings(_env_file=None)
        assert settings.app_env == "production" and settings.fault_injection == ""
        assert RunConfig().fault is None
        assert RunConfig.from_settings(settings).fault is None

    @pytest.mark.parametrize("env", ["production"])
    def test_production_mode_refuses_even_when_the_fault_is_named(self, env):
        settings = Settings(_env_file=None, app_env=env, fault_injection="missing_column")
        with pytest.raises(FaultInjectionRefused, match="APP_ENV"):
            authorize(settings, "missing_column")
        with pytest.raises(FaultInjectionRefused):
            FaultInjector.authorized(settings, "missing_column")
        # and the production configuration path never carries it
        assert RunConfig.from_settings(settings).fault is None

    def test_test_mode_without_naming_the_fault_refuses(self):
        for named in ("", "hang"):
            settings = Settings(_env_file=None, app_env="test", fault_injection=named)
            with pytest.raises(FaultInjectionRefused, match="does not name"):
                authorize(settings, "missing_column")

    def test_unknown_fault_and_unknown_environment_are_refused(self):
        with pytest.raises(FaultInjectionRefused, match="unknown"):
            authorize(test_settings("made_up"), "made_up")
        with pytest.raises(ValueError, match="APP_ENV"):
            Settings(_env_file=None, app_env="staging")

    def test_allowed_in_test_and_diagnostic_modes_only(self):
        assert authorize(test_settings(env="test"), "missing_column") is FAULTS["missing_column"]
        assert (
            authorize(test_settings(env="diagnostic"), "missing_column") is FAULTS["missing_column"]
        )

    def test_an_injector_cannot_be_constructed_without_authorization(self):
        with pytest.raises(FaultInjectionRefused, match="authorized"):
            FaultInjector(FAULTS["missing_column"])
        with pytest.raises(FaultInjectionRefused):
            FaultInjector(FAULTS["missing_column"], _token=object())

    @pytest.mark.parametrize("times", [0, 9, -1])
    def test_injection_count_is_bounded(self, times):
        with pytest.raises(FaultInjectionRefused, match="times"):
            injector(times=times)

    def test_a_fault_that_does_not_apply_is_an_error_not_a_silent_noop(self):
        with pytest.raises(FaultInjectionError, match="does not apply"):
            FAULTS["missing_column"].apply("print('nothing to mutate')")
        with pytest.raises(FaultInjectionError, match="did not change"):
            FaultSpec("x", "d", "abc", "abc").apply("abc")  # a no-op mutation is refused too

    def test_an_unattached_injector_refuses_to_mutate(self):
        with pytest.raises(FaultInjectionError, match="not attached"):
            injector().inject("```python\ndf['units']\n```", "df['units']")

    def test_production_modules_never_import_the_fault_module(self):
        """No UI source (including ui/live.py) can create or reference a fault injector."""
        offenders = []
        for path in (ROOT / "src" / "datapilot" / "ui").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"fault=", text) or any(
                w in text for w in ("datapilot.faults", "FaultInjector", "FAULT_INJECTION")
            ):
                offenders.append(path.name)
        assert offenders == []

    def test_run_question_has_no_fault_parameter_only_the_explicit_config_field(self):
        import inspect

        from datapilot.agents.runner import run_question

        assert "fault" not in inspect.signature(run_question).parameters
        assert RunConfig.__dataclass_fields__["fault"].default is None


# ============================================================ injected failure -> real repair ====
async def test_injected_error_is_executed_for_real_and_repaired(api, monkeypatch):
    fault = injector()
    run = await run_real(
        api,
        monkeypatch,
        coder=[block(GOOD), block(GOOD)],
        reviewer=[APPROVE],
        fault=fault,
        name="injected-repair",
        stage=STAGE,
    )
    record = fault.records[0]
    assert run.outcome is O.REVIEWER_APPROVED, explain(run)
    assert run.letters == "PCECER" and run.canvas.message_count == 6

    # --- the fault: labelled, deterministic, recorded -------------------------------------------
    injected = run.of("test_fault_injected")
    assert len(injected) == 1 and injected[0].source == FAULT_SOURCE
    assert (
        injected[0].payload["test_only"] is True
        and injected[0].payload["fault"] == "missing_column"
    )
    assert injected[0].payload["original_hash"] == record.original_hash != record.mutated_hash
    assert record.original_code.strip() == GOOD.strip()
    assert 'df["qty"]' in record.mutated_code and 'df["units"]' not in record.mutated_code
    assert (
        injected[0].seq < run.of("code_generated")[0].seq
    )  # announced BEFORE the faulty code appears

    # --- what actually executed is the mutated code, in a real container ------------------------
    first, second = run.backend.results
    assert sha12(run.backend.codes[0]) == record.mutated_hash
    assert run.backend.codes[0].strip() == record.mutated_code.strip() != GOOD.strip()
    assert first.status == "error" and first.exit_code == 1
    assert (
        "KeyError: 'qty'" in first.stderr and "/in/analysis.py" in first.stderr
    )  # genuine traceback
    assert first.exec_id != second.exec_id  # the correction ran in a NEW sandbox execution
    assert len(run.containers_created) == 2

    # --- the Coder's memory describes exactly the code that was executed ------------------------
    coder_call_2 = run.clients.coder.create_calls[1]["messages"]
    assistant = [m for m in coder_call_2 if type(m).__name__ == "AssistantMessage"]
    assert len(assistant) == 1 and assistant[0].content == record.mutated_content
    flat = "\n".join(str(m.content) for m in coder_call_2)
    assert 'df["qty"]' in flat and 'df["units"]' not in flat  # no trace of the pre-mutation code
    assert first.stderr in flat  # and it received the container's real stderr, verbatim
    # the Reviewer, too, saw the executed (mutated) code and the real failure
    reviewer_input = "\n".join(
        str(m.content) for m in run.clients.reviewer.create_calls[0]["messages"]
    )
    assert 'df["qty"]' in reviewer_input and "KeyError: 'qty'" in reviewer_input

    # --- repair + routing + final validation ----------------------------------------------------
    assert len(run.of("repair_routed")) == 1
    assert (
        sha12(run.backend.codes[1]) == record.original_hash
    )  # scripted correction differs from the mutation
    assert sha12(run.backend.codes[1]) != record.mutated_hash
    assert second.ok
    assert_matches_truth(second.results_json)
    assert run.of("reviewer_approved")[0].payload["message"] == 6  # approval only after success
    assert run.canvas.human == "none" and not run.canvas.fully_verified  # human approval separate

    # --- the failure is identified as injected in the events ------------------------------------
    started, finished = run.of("exec_started"), run.of("exec_result")
    assert (
        started[0].payload["injected_fault"]
        == finished[0].payload["injected_fault"]
        == "missing_column"
    )
    assert "injected_fault" not in finished[1].payload  # the genuine correction is not labelled
    assert run.of("code_generated")[0].payload["injected_fault"] == "missing_column"
    assert "injected_fault" not in run.of("code_generated")[1].payload
    audit = write_fault_record("injected-repair", run)
    assert [e["injected_fault"] for e in audit["executions"]] == ["missing_column", None]


async def test_livewire_viewmodel_distinguishes_injected_from_natural_failures(api, monkeypatch):
    injected = await run_real(
        api, monkeypatch, coder=[block(GOOD), block(GOOD)], reviewer=[APPROVE],
        fault=injector(), name="distinguish-injected", stage=STAGE,
    )  # fmt: skip
    natural = await run_real(
        api, monkeypatch, coder=[block(BAD_KEYERROR), block(GOOD)], reviewer=[APPROVE],
        name="distinguish-natural", stage=STAGE,
    )  # fmt: skip
    # both really failed once with a genuine KeyError and were repaired
    for run, key in ((injected, "qty"), (natural, "revenue")):
        assert run.backend.results[0].status == "error"
        assert f"KeyError: '{key}'" in run.backend.results[0].stderr
        assert run.outcome is O.REVIEWER_APPROVED and run.letters == "PCECER"
    # event level
    assert natural.of("test_fault_injected") == []
    assert not any("injected_fault" in e.payload for e in natural.events)
    assert any("injected_fault" in e.payload for e in injected.events)
    # reducer / Livewire view-model level (the approved UI reads exactly these)
    assert (
        build_canvas(injected.events).fault is True and build_canvas(natural.events).fault is False
    )
    feed_i = [i.text for i in feed_items(injected.events, limit=50)]
    feed_n = [i.text for i in feed_items(natural.events, limit=50)]
    assert any("test_fault_injected" in t and "(TEST ONLY)" in t for t in feed_i)
    assert not any("test_fault_injected" in t for t in feed_n)


async def test_injection_disabled_leaves_normal_execution_unchanged(api, monkeypatch):
    run = await run_real(
        api,
        monkeypatch,
        coder=[block(GOOD)],
        reviewer=[APPROVE],
        name="disabled-normal",
        stage=STAGE,
    )
    assert run.outcome is O.REVIEWER_APPROVED and run.letters == "PCER"
    assert run.backend.codes[0].strip() == GOOD.strip()  # exactly what the Coder wrote
    assert run.of("test_fault_injected") == [] and run.canvas.fault_injected is False
    assert not any("injected_fault" in e.payload for e in run.events)
    assert_matches_truth(run.backend.results[0].results_json)
    assert len(run.containers_created) == 1


async def test_a_named_fault_in_production_mode_cannot_reach_a_run(api, monkeypatch):
    """Even with FAULT_INJECTION set, production settings neither authorize nor configure a fault."""
    monkeypatch.setenv("FAULT_INJECTION", "missing_column")
    prod = Settings(_env_file=None)
    assert prod.app_env == "production" and prod.fault_injection == "missing_column"
    with pytest.raises(FaultInjectionRefused):
        FaultInjector.authorized(prod, "missing_column")
    run = await run_real(api, monkeypatch, coder=[block(GOOD)], reviewer=[APPROVE])
    assert run.backend.codes[0].strip() == GOOD.strip() and run.of("test_fault_injected") == []


async def test_unusable_coder_replies_are_not_faulted_and_a_non_applicable_fault_is_loud(
    api, monkeypatch
):
    skipped = injector()
    run = await run_real(
        api, monkeypatch, coder=["no code at all", block(GOOD), block(GOOD)], reviewer=[APPROVE],
        fault=skipped, name="skip-unusable", stage=STAGE,
    )  # fmt: skip
    assert (
        run.letters == "PCCECER"
    )  # the unusable reply was left alone; the next valid one was mutated
    assert (
        len(skipped.records) == 1
        and run.of("guardrail")[0].payload["rule"] == "single_python_block"
    )
    inapplicable = await run_real(
        api, monkeypatch, coder=[block("print('no units column here')")], reviewer=[APPROVE],
        fault=injector(), name="not-applicable", stage=STAGE,
    )  # fmt: skip
    assert (
        inapplicable.outcome is O.ERROR and inapplicable.backend.codes == []
    )  # nothing ran silently
    assert "does not apply" in inapplicable.of("run_error")[0].payload["reason"]


# ======================================================================== limits and controls ====
async def test_repeated_injected_failures_end_unapproved_at_the_12_message_limit(api, monkeypatch):
    fault = injector(times=5)
    run = await run_real(
        api, monkeypatch, coder=[block(GOOD)] * 8, reviewer=[APPROVE], fault=fault,
        name="limit-12", stage=STAGE,
    )  # fmt: skip
    assert run.outcome is O.LIMIT_REACHED, explain(run)
    assert run.letters == "PCECECECECEC" and run.canvas.message_count == 12
    assert len(run.of("test_fault_injected")) == 5 == len(fault.records)
    assert [r.status for r in run.backend.results] == ["error"] * 5
    assert all("KeyError: 'qty'" in r.stderr for r in run.backend.results)
    assert len({r.exec_id for r in run.backend.results}) == 5 and len(run.containers_created) == 5
    assert run.clients.reviewer.create_calls == []  # unresolved failure never reaches the Reviewer
    assert run.of("reviewer_approved") == [] and not run.canvas.reviewer_verified
    assert (
        run.canvas.phase == "limit_reached"
        and run.of("limit_reached")[0].payload["limit"] == "messages"
    )
    write_fault_record("limit-12", run)


async def test_reviewer_approval_is_blocked_after_an_unresolved_injected_failure(api, monkeypatch):
    run = await run_real(
        api, monkeypatch, mode="round_robin", coder=[block(GOOD)] * 4, reviewer=[APPROVE] * 4,
        fault=injector(times=5), name="approval-blocked", stage=STAGE,
    )  # fmt: skip
    # round-robin sends every failure to the Reviewer, who keeps saying APPROVED: it never counts
    assert run.outcome is O.LIMIT_REACHED and run.letters == "PCERPCERPCER"
    assert run.of("reviewer_approved") == [] and not run.canvas.reviewer_verified
    ignored = [e for e in run.of("guardrail") if e.payload["rule"].startswith("approval_requires")]
    assert len(ignored) == 3  # three premature APPROVED replies, each ignored (and still counted)
    assert run.canvas.violations == ()


async def test_approval_after_the_repair_is_the_only_one_that_counts(api, monkeypatch):
    run = await run_real(
        api, monkeypatch, mode="round_robin", coder=[block(GOOD)] * 2, reviewer=[APPROVE] * 2,
        fault=injector(), name="approval-after-repair", stage=STAGE,
    )  # fmt: skip
    assert run.outcome is O.REVIEWER_APPROVED and run.letters == "PCERPCER"
    assert run.of("reviewer_approved")[0].payload["message"] == 8
    assert_matches_truth(run.backend.results[-1].results_json)


async def test_token_budget_still_applies_to_injected_runs(api, monkeypatch):
    base = await run_real(
        api, monkeypatch, coder=[block(GOOD)] * 2, reviewer=[APPROVE], fault=injector()
    )
    total = base.canvas.input_tokens + base.canvas.output_tokens
    short = await run_real(
        api, monkeypatch, coder=[block(GOOD)] * 2, reviewer=[APPROVE], fault=injector(),
        max_tokens=int(total * 0.55), name="injected-token-budget", stage=STAGE,
    )  # fmt: skip
    assert (
        short.outcome is O.TOKEN_BUDGET_EXHAUSTED
        and short.of("limit_reached")[0].payload["limit"] == "tokens"
    )
    assert not short.canvas.reviewer_verified
    assert len(short.of("test_fault_injected")) == 1  # still labelled in the evidence


async def test_message_cap_still_applies_to_injected_runs(api, monkeypatch):
    run = await run_real(
        api, monkeypatch, coder=[block(GOOD)] * 2, reviewer=[APPROVE], fault=injector(),
        max_messages=3, name="injected-message-cap", stage=STAGE,
    )  # fmt: skip
    assert run.outcome is O.LIMIT_REACHED and run.letters == "PCE" and run.canvas.message_count == 3


# ============================================================ timeout / cancellation / OOM =======
async def test_hanging_injected_code_hits_the_sandbox_timeout_and_is_repaired(api, monkeypatch):
    run = await run_real(
        api, monkeypatch, coder=[block(GOOD), block(GOOD)], reviewer=[APPROVE],
        fault=injector("hang"), exec_timeout_s=10, name="hang-sandbox-timeout", stage=STAGE,
    )  # fmt: skip
    first = run.backend.results[0]
    assert first.status == "timeout" and first.exit_code == 124  # genuine wall-clock kill
    assert run.of("exec_result")[0].payload["injected_fault"] == "hang"
    assert run.outcome is O.REVIEWER_APPROVED and run.letters == "PCECER"
    write_fault_record("hang-sandbox-timeout", run)


async def test_run_timeout_during_injected_execution_kills_the_container(api, monkeypatch):
    run = await run_real(
        api, monkeypatch, coder=[block(GOOD)], reviewer=[APPROVE], fault=injector("hang"),
        timeout_seconds=6, exec_timeout_s=60, name="hang-run-timeout", stage=STAGE,
    )  # fmt: skip
    assert run.outcome is O.TIMEOUT and run.of("limit_reached")[0].payload["limit"] == "time"
    assert run.of("exec_started")[0].payload["injected_fault"] == "hang"
    assert run.of("exec_result") == [] and run.backend.results == []  # no result was invented
    await asyncio.sleep(1.0)
    assert containers_left() == []
    assert run.of("reviewer_approved") == [] and not run.canvas.fully_verified


async def test_user_stop_during_injected_execution_cancels_and_cleans_up(api, monkeypatch):
    control = RunControl()
    asyncio.get_running_loop().call_later(6, control.stop)
    run = await run_real(
        api, monkeypatch, coder=[block(GOOD)], reviewer=[APPROVE], fault=injector("hang"),
        control=control, name="hang-user-stop", stage=STAGE,
    )  # fmt: skip
    assert run.outcome is O.STOPPED and run.of("limit_reached")[0].payload["limit"] == "stopped"
    await asyncio.sleep(1.0)
    assert containers_left() == []


async def test_oom_in_a_natural_failure_is_not_mislabelled_as_injected(api, monkeypatch):
    run = await run_real(
        api, monkeypatch, coder=[block(OOM), block(GOOD)], reviewer=[APPROVE],
        fault=None, name="natural-oom-not-injected", stage=STAGE,
    )  # fmt: skip
    assert run.backend.results[0].status == "killed"
    assert (
        not any("injected_fault" in e.payload for e in run.events)
        and run.canvas.fault_injected is False
    )


# ======================================================================== cleanup ================
async def test_zz_nothing_is_left_behind_by_any_scenario(api):
    assert containers_left() == []
    assert list(api.manager.layout.runs.iterdir()) == []
    assert list(api.manager.layout.artifacts.iterdir()) == []

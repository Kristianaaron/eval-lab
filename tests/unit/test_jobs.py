"""Unit tests: job orchestrator state machine, restore, leakage guard."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from eval_lab.schemas.job import Job, JobState, transition
from eval_lab.schemas.models import InputSpec, TaskSpec
from eval_lab.services.leakage import check_leakage
from eval_lab.services.orchestrator import JobContext, JobOrchestrator
from eval_lab.storage.jobs import JobStore

# ---------------------------------------------------------------------------
# state machine
# ---------------------------------------------------------------------------


def test_transition_valid_and_invalid() -> None:
    assert transition(JobState.queued, JobState.running) == JobState.running
    assert transition(JobState.running, JobState.completed) == JobState.completed
    assert transition(JobState.running, JobState.paused) == JobState.paused
    # Resume a recoverable-failed job is allowed.
    assert transition(JobState.failed_recoverable, JobState.queued) == JobState.queued
    with pytest.raises(ValueError):
        transition(JobState.completed, JobState.running)
    with pytest.raises(ValueError):
        transition(JobState.running, JobState.draft)


def test_orchestrator_completes_and_persists(tmp_path: Path) -> None:
    from threading import Event

    release = Event()
    scratch: dict = {}

    def executor(job: Job, ctx: JobContext) -> None:
        ctx.set_stage("working")
        ctx.set_progress(3, 5, detail="task-3")
        scratch["stage"] = ctx.job_id
        release.wait(timeout=5)
        ctx.set_progress(5, 5)

    orc = JobOrchestrator(tmp_path / "jobs")
    orc.register("peek", executor)
    job = orc.submit("peek", {"x": 1})
    # Let it reach running and progress.
    for _ in range(200):
        j = orc.get(job.job_id)
        if j.progress.done == 3:
            break
        time.sleep(0.01)
    j = orc.get(job.job_id)
    assert j.state == JobState.running
    assert j.current_stage == "working"
    assert j.progress.done == 3 and j.progress.total == 5

    release.set()
    for _ in range(200):
        j = orc.get(job.job_id)
        if j.state == JobState.completed:
            break
        time.sleep(0.01)
    j = orc.get(job.job_id)
    assert j.state == JobState.completed
    assert j.progress.done == 5
    assert j.started_at is not None and j.finished_at is not None


def test_orchestrator_cancel_requested(tmp_path: Path) -> None:
    from threading import Event

    release = Event()

    def executor(job: Job, ctx: JobContext) -> None:
        release.wait(timeout=5)

    orc = JobOrchestrator(tmp_path / "jobs")
    orc.register("hang", executor)
    job = orc.submit("hang", {})
    time.sleep(0.05)
    orc.cancel(job.job_id)
    j = orc.get(job.job_id)
    assert j.cancel_requested is True
    release.set()
    for _ in range(200):
        j = orc.get(job.job_id)
        if j.state == JobState.cancelled:
            break
        time.sleep(0.01)
    assert orc.get(job.job_id).state == JobState.cancelled


def test_restore_flags_orphaned_active_jobs(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    store.save(Job(job_id="evaluation-orphan000001", kind="evaluation", state=JobState.running))
    store.save(Job(job_id="evaluation-done0000001", kind="evaluation", state=JobState.completed))
    orc = JobOrchestrator(tmp_path / "jobs")
    orphan = orc.get("evaluation-orphan000001")
    assert orphan.state == JobState.failed_recoverable
    assert orphan.interrupted is True
    # Completed jobs are left untouched.
    assert orc.get("evaluation-done0000001").state == JobState.completed


# ---------------------------------------------------------------------------
# leakage guard
# ---------------------------------------------------------------------------


def _task(i: str, partition: str) -> TaskSpec:
    return TaskSpec(
        id=f"t.{i}",
        name=f"task {i}",
        description="",
        version=1,
        input=InputSpec(instruction_file="prompt.md"),
        data_partition=partition,
    )


def test_leakage_detects_calibration_overlap() -> None:
    cal = {"t.1"}
    leak = check_leakage(
        [_task("1", "held_out_evaluation"), _task("2", "held_out_evaluation")],
        calibration_ids=cal,
    )
    assert leak.detected is True
    assert leak.blocked is True
    assert leak.overlapping_task_ids == ["t.1"]
    assert "cannot be treated as held-out" in leak.message


def test_leakage_clean_when_disjoint() -> None:
    leak = check_leakage([_task("9", "held_out_evaluation")])
    assert leak.detected is False
    assert leak.blocked is False
    assert leak.overlapping_task_ids == []

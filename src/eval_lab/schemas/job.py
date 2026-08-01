"""Generic persisted job schema + state machine (spec 14, correction #1).

A single orchestrator drives every long-running operation (evaluation, atlas,
experiment, derivative build, …). The coarse :class:`JobState` is owned by the
orchestrator; per-kind executors report a human ``current_stage`` and numeric
progress so the GUI shows real, non-fake progress (spec 14.3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobState(StrEnum):
    draft = "draft"
    queued = "queued"
    running = "running"
    pausing = "pausing"
    paused = "paused"
    resuming = "resuming"
    cancelling = "cancelling"
    cancelled = "cancelled"
    completed = "completed"
    completed_with_warnings = "completed_with_warnings"
    failed_recoverable = "failed_recoverable"
    failed = "failed"


TERMINAL_STATES = frozenset(
    {
        JobState.cancelled,
        JobState.completed,
        JobState.completed_with_warnings,
        JobState.failed,
        JobState.failed_recoverable,
    }
)
ACTIVE_STATES = frozenset(
    {
        JobState.draft,
        JobState.queued,
        JobState.running,
        JobState.pausing,
        JobState.paused,
        JobState.resuming,
        JobState.cancelling,
    }
)

TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.draft: {JobState.queued, JobState.cancelled, JobState.failed},
    JobState.queued: {JobState.running, JobState.cancelling, JobState.cancelled, JobState.failed},
    JobState.running: {
        JobState.pausing,
        JobState.cancelling,
        JobState.paused,
        JobState.completed,
        JobState.completed_with_warnings,
        JobState.failed,
        JobState.failed_recoverable,
    },
    JobState.pausing: {JobState.paused, JobState.running, JobState.cancelling, JobState.failed},
    JobState.paused: {JobState.resuming, JobState.cancelling, JobState.cancelled, JobState.failed},
    JobState.resuming: {JobState.running, JobState.pausing, JobState.cancelling, JobState.failed},
    JobState.cancelling: {JobState.cancelled, JobState.failed},
    JobState.cancelled: set(),
    JobState.completed: set(),
    JobState.completed_with_warnings: set(),
    JobState.failed: set(),
    JobState.failed_recoverable: {JobState.queued, JobState.running},  # resume
}


def transition(old: JobState, new: JobState) -> JobState:
    allowed = TRANSITIONS.get(old, set())
    if new not in allowed and old != new:
        raise ValueError(f"invalid job transition: {old.value} -> {new.value}")
    return new


class JobProgress(BaseModel):
    total: int | None = None
    done: int = 0
    detail: str | None = None


class JobResult(BaseModel):
    """References to the artifacts a job produced (stored, not inline blobs)."""

    run_ids: list[str] = Field(default_factory=list)
    artifact_paths: list[str] = Field(default_factory=list)
    report_path: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Job(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    kind: str
    name: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    state: JobState = JobState.draft
    current_stage: str | None = None
    progress: JobProgress = Field(default_factory=JobProgress)
    error: str | None = None
    interrupted: bool = False
    cancel_requested: bool = False
    result: JobResult = Field(default_factory=JobResult)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None

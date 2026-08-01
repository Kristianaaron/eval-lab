"""Job orchestrator engine (spec 14, correction #1).

Drives every long-running operation in a background thread with persisted
state, real progress, safe-boundary cancellation, and restart recovery.
Per-kind executors stay decoupled from the harness internals they run.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval_lab.schemas.job import (
    ACTIVE_STATES,
    Job,
    JobProgress,
    JobResult,
    JobState,
    transition,
)

Executor = Callable[["Job", "JobContext"], None]
_MISSING = object()


class JobCancelled(Exception):
    """Raised by an executor slot to abort cleanly at a safe boundary."""


class JobContext:
    """Controls/journal a running job from inside an executor."""

    def __init__(self, orchestrator: JobOrchestrator, job_id: str) -> None:
        self._orchestrator = orchestrator
        self.job_id = job_id
        self.cancel_requested = False
        self.pause_requested = False
        self._final_state: JobState | None = None

    def set_stage(self, stage: str) -> None:
        self._orchestrator._mutate(self.job_id, lambda j: setattr(j, "current_stage", stage))

    def set_progress(self, done: int, total: int | None = None, detail: str | None = None) -> None:
        self._orchestrator._mutate(
            self.job_id,
            lambda j: setattr(j, "progress", JobProgress(total=total, done=done, detail=detail)),
        )

    def set_result(self, result: JobResult) -> None:
        self._orchestrator._mutate(self.job_id, lambda j: setattr(j, "result", result))

    def should_stop(self) -> bool:
        """True when the orchestrator wants the executor to stop at a safe boundary."""
        job = self._orchestrator.get(self.job_id)
        if job is None:
            return True
        if job.cancel_requested:
            self.cancel_requested = True
            return True
        if job.state in (JobState.cancelling, JobState.pausing):
            self.pause_requested = job.state == JobState.pausing
            return True
        return False

    def finish(self, state: JobState) -> None:
        self._final_state = state


class JobOrchestrator:
    def __init__(self, root: str | Path) -> None:
        from eval_lab.storage.jobs import JobStore

        self.store = JobStore(root)
        self._executors: dict[str, Executor] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._restore_interrupted()

    def register(self, kind: str, executor: Executor) -> None:
        self._executors[kind] = executor

    # -- lifecycle ----------------------------------------------------------
    def submit(self, kind: str, config: dict[str, Any], *, name: str | None = None) -> Job:
        if kind not in self._executors:
            raise ValueError(f"no executor registered for kind: {kind}")
        job = Job(job_id=self.store.new_id(kind), kind=kind, name=name, config=config)
        self.store.save(job)
        self._to(job.job_id, JobState.queued)
        thread = threading.Thread(
            target=self._run, args=(job.job_id,), daemon=True, name=job.job_id
        )
        with self._lock:
            self._threads[job.job_id] = thread
        thread.start()
        return job

    def get(self, job_id: str) -> Job | None:
        return self.store.get(job_id)

    def list(self, *, kind: str | None = None) -> list[Job]:
        return sorted(self.store.list(kind=kind), key=lambda j: j.created_at, reverse=True)

    def cancel(self, job_id: str) -> Job | None:
        job = self.get(job_id)
        if job is None or job.state in (
            JobState.cancelled,
            JobState.completed,
            JobState.completed_with_warnings,
            JobState.failed,
        ):
            return job
        self._mutate(job_id, lambda j: setattr(j, "cancel_requested", True))
        if job.state not in (JobState.running, JobState.paused):
            self._to(job_id, JobState.cancelling)
        return self.get(job_id)

    def resume(self, job_id: str) -> Job | None:
        job = self.get(job_id)
        if job is not None and job.state == JobState.paused:
            self._to(job_id, JobState.resuming)
            self._to(job_id, JobState.queued)
            thread = threading.Thread(target=self._run, args=(job_id,), daemon=True, name=job_id)
            with self._lock:
                self._threads[job_id] = thread
            thread.start()
        return self.get(job_id)

    # -- worker -------------------------------------------------------------
    def _run(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is None:
            return
        executor = self._executors.get(job.kind)
        if executor is None:
            self._fail(job_id, f"no executor for kind: {job.kind}")
            return
        if job.state in (JobState.queued, JobState.resuming):
            self._to(job_id, JobState.running)
        self._mutate(job_id, lambda j: setattr(j, "started_at", j.started_at or datetime.now(UTC)))
        ctx = JobContext(self, job_id)
        try:
            executor(job, ctx)
        except JobCancelled:
            pass
        except Exception as exc:  # noqa: BLE001 - persist any failure
            self._fail(job_id, str(exc))
            with self._lock:
                self._threads.pop(job_id, None)
            return

        job = self.get(job_id)
        if ctx.cancel_requested or (
            job is not None and (job.state == JobState.cancelling or job.cancel_requested)
        ):
            self._finish(job_id, JobState.cancelled)
        elif ctx.pause_requested or (job is not None and job.state == JobState.pausing):
            self._finish(job_id, JobState.paused)
        else:
            final = ctx._final_state or JobState.completed
            if job is not None and job.state in (JobState.running,):
                self._finish(job_id, final)
        with self._lock:
            self._threads.pop(job_id, None)

    # -- persistence helpers -------------------------------------------------
    def _to(self, job_id: str, state: JobState) -> None:
        job = self.get(job_id)
        if job is None:
            return
        transition(job.state, state)
        job.state = state
        job.updated_at = datetime.now(UTC)
        if job.started_at is None and state == JobState.running:
            job.started_at = datetime.now(UTC)
        if state in (
            JobState.completed,
            JobState.completed_with_warnings,
            JobState.failed,
            JobState.failed_recoverable,
            JobState.cancelled,
            JobState.paused,
        ):
            job.finished_at = datetime.now(UTC)
        self.store.save(job)

    def _finish(self, job_id: str, state: JobState) -> None:
        job = self.get(job_id)
        if job is None:
            return
        job.state = state
        job.finished_at = datetime.now(UTC)
        job.updated_at = datetime.now(UTC)
        self.store.save(job)

    def _fail(self, job_id: str, error: str) -> None:
        job = self.get(job_id)
        if job is None:
            return
        job.state = JobState.failed
        job.error = error
        job.finished_at = datetime.now(UTC)
        job.updated_at = datetime.now(UTC)
        self.store.save(job)

    def _mutate(self, job_id: str, fn: Callable[[Job], object]) -> None:
        job = self.get(job_id)
        if job is None:
            return
        fn(job)
        job.updated_at = datetime.now(UTC)
        self.store.save(job)

    def _restore_interrupted(self) -> None:
        """Flag jobs left active by a previous process as recoverable-failed."""
        now = datetime.now(UTC)
        for job in self.store.list():
            if job.state in ACTIVE_STATES:
                job.state = JobState.failed_recoverable
                job.interrupted = True
                job.error = (
                    "Interrupted by process restart (job was active when the "
                    "previous process exited)."
                )
                job.finished_at = now
                self.store.save(job)

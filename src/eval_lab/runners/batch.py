"""Batch and suite runner (spec 10.4, 10.5)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol, runtime_checkable

from eval_lab.runners.direct import RunContext, RunResult
from eval_lab.schemas.models import SuiteSpec, TaskSpec


@runtime_checkable
class Executor(Protocol):
    def execute_task(self, task: TaskSpec, context: RunContext) -> RunResult: ...


def run_batch(
    runner: Executor,
    tasks: Iterable[TaskSpec],
    context_factory: Callable[[TaskSpec], RunContext],
) -> list[RunResult]:
    """Run a sequence of tasks, collecting results (no dedup of failures)."""
    results: list[RunResult] = []
    for task in tasks:
        context = context_factory(task)
        results.append(runner.execute_task(task, context))
    return results


def run_suite(
    runner: Executor,
    suite: SuiteSpec,
    tasks_by_id: dict[str, TaskSpec],
    context_factory: Callable[[TaskSpec], RunContext],
) -> list[RunResult]:
    """Run every task referenced by a suite, respecting per-ref repetition count."""
    results: list[RunResult] = []
    for ref in suite.tasks:
        task = tasks_by_id.get(ref.task_id)
        if task is None:
            continue
        reps = ref.repetitions or 1
        for _ in range(reps):
            context = context_factory(task)
            results.append(runner.execute_task(task, context))
    return results

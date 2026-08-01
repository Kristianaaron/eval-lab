"""Weighted suite aggregation (spec 8.1B, 17.4, Phase 5)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from eval_lab.analysis.rows import RunRow
from eval_lab.analysis.statistics import mean, weighted_mean


@dataclass(frozen=True)
class TaskRow:
    """Per-task aggregate for one suite run group."""

    task_id: str
    weight: float
    score: float | None
    passed: bool | None
    duration_s: float | None
    labels: Mapping[str, frozenset[str]]
    n_runs: int


@dataclass(frozen=True)
class SuiteAggregate:
    """Weighted suite result; unweighted raw values are always included too."""

    weighted_score: float
    unweighted_score: float
    weighted_pass_rate: float
    unweighted_pass_rate: float
    task_count: int
    scored_tasks: int
    weight_sum: float
    per_task: tuple[TaskRow, ...]

    def slice(self, axis: str) -> dict[str, SliceAggregate]:
        from eval_lab.analysis.slices import slice_tasks

        return slice_tasks(self.per_task, axis)


@dataclass(frozen=True)
class SliceAggregate:
    """Aggregate for one label value (raw and weighted)."""

    label: str
    task_count: int
    scored_tasks: int
    weighted_score: float
    unweighted_score: float
    weighted_pass_rate: float
    unweighted_pass_rate: float


def _task_passed(runs: Sequence[RunRow]) -> bool | None:
    known = [r.passed for r in runs if r.passed is not None]
    if not known:
        return None
    return all(known)


def _task_score(runs: Sequence[RunRow]) -> float | None:
    scores = [r.score for r in runs if r.score is not None]
    return mean(scores) if scores else None


def build_task_rows(
    runs: Sequence[RunRow],
    weight_by_task: Mapping[str, float] | None = None,
) -> list[TaskRow]:
    """Collapse per-repetition rows into one row per task.

    ``weight_by_task`` supplies per-task suite weights (default 1.0). Labels are
    merged from the resolved rows (each run already carries its task's labels).
    """
    by_task: dict[str, list[RunRow]] = {}
    for r in runs:
        by_task.setdefault(r.task_id, []).append(r)

    rows: list[TaskRow] = []
    for task_id in sorted(by_task):
        group = by_task[task_id]
        weight = float(weight_by_task.get(task_id, 1.0)) if weight_by_task else 1.0
        labels: Mapping[str, frozenset[str]] = group[0].labels
        rows.append(
            TaskRow(
                task_id=task_id,
                weight=weight,
                score=_task_score(group),
                passed=_task_passed(group),
                duration_s=next((r.duration_s for r in group if r.duration_s is not None), None),
                labels=labels,
                n_runs=len(group),
            )
        )
    return rows


def aggregate_suite(
    runs: Sequence[RunRow],
    weight_by_task: Mapping[str, float] | None = None,
) -> SuiteAggregate:
    """Compute the weighted suite composite from raw runs."""
    return aggregate_task_rows(build_task_rows(runs, weight_by_task))


def aggregate_task_rows(rows: Sequence[TaskRow]) -> SuiteAggregate:
    """Compute the weighted suite composite from (possibly reweighted) task rows."""
    scored = [r for r in rows if r.score is not None]
    passed = [r for r in rows if r.passed is not None]
    scored_scores = [float(r.score) for r in scored if r.score is not None]
    scored_weights = [r.weight for r in scored]
    pass_flags = [1.0 if r.passed else 0.0 for r in passed]
    pass_weights = [r.weight for r in passed]

    weighted_score = weighted_mean(scored_scores, scored_weights) if scored_scores else 0.0
    unweighted_score = mean(scored_scores)
    weighted_pass_rate = weighted_mean(pass_flags, pass_weights) if pass_flags else 0.0
    unweighted_pass_rate = mean(pass_flags)

    return SuiteAggregate(
        weighted_score=weighted_score,
        unweighted_score=unweighted_score,
        weighted_pass_rate=weighted_pass_rate,
        unweighted_pass_rate=unweighted_pass_rate,
        task_count=len(rows),
        scored_tasks=len(scored),
        weight_sum=sum(r.weight for r in rows),
        per_task=tuple(rows),
    )

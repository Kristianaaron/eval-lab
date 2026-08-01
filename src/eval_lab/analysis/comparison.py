"""Paired A/B comparison engine (spec 17.2, Phase 5)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from eval_lab.analysis.regression import Regression, detect_regressions
from eval_lab.analysis.rows import RunRow
from eval_lab.analysis.significance import (
    is_significant,
    mean_paired_delta,
    median_paired_delta,
    paired_confidence_interval,
    win_tie_loss,
)
from eval_lab.analysis.statistics import mean


@dataclass(frozen=True)
class TaskPair:
    """Per-task comparison between a base and candidate configuration."""

    task_id: str
    base_mean: float
    candidate_mean: float
    base_passed: bool | None
    candidate_passed: bool | None
    base_n: int
    candidate_n: int


@dataclass(frozen=True)
class ResourceDelta:
    """Mean candidate-vs-base delta for one numeric resource over matched tasks."""

    resource: str
    mean_delta: float
    tasks: int


@dataclass(frozen=True)
class ComparisonResult:
    base_label: str
    candidate_label: str
    tasks: tuple[TaskPair, ...]
    mean_delta: float
    median_delta: float
    ci: tuple[float | None, float | None]
    wins: int
    ties: int
    losses: int
    regressions: tuple[Regression, ...]
    improvements: tuple[Regression, ...]
    failure_transitions: dict[str, int]
    resource_deltas: tuple[ResourceDelta, ...]
    significant: bool
    sample_size: int

    @property
    def matched_task_ids(self) -> list[str]:
        return [t.task_id for t in self.tasks]


def _task_mean(runs: Sequence[RunRow], task_id: str) -> float | None:
    scores = [r.score for r in runs if r.task_id == task_id and r.score is not None]
    return mean(scores) if scores else None


def _task_passed(runs: Sequence[RunRow], task_id: str) -> bool | None:
    """True only when every repetition passed; False when any failed."""
    known = [r.passed for r in runs if r.task_id == task_id and r.passed is not None]
    if not known:
        return None
    return all(known)


def _task_count(runs: Sequence[RunRow], task_id: str) -> int:
    return sum(1 for r in runs if r.task_id == task_id)


def _group_by_task(runs: Iterable[RunRow]) -> dict[str, list[RunRow]]:
    grouped: dict[str, list[RunRow]] = defaultdict(list)
    for r in runs:
        grouped[r.task_id].append(r)
    return grouped


def compare_groups(
    base_runs: Sequence[RunRow],
    candidate_runs: Sequence[RunRow],
    *,
    base_label: str = "base",
    candidate_label: str = "candidate",
    regress_threshold: float = 0.05,
    min_samples: int = 3,
    confidence: float = 0.95,
    n_resamples: int = 2000,
    seed: int = 1234,
) -> ComparisonResult:
    """Pair a base and candidate run group on shared tasks and compare them.

    Tasks appearing in both groups are matched by id. Deltas are
    ``candidate_mean - base_mean`` (positive = candidate better). Regression
    detection flags tasks where the candidate is worse than the base beyond
    ``regress_threshold``.
    """
    base_by_task = _group_by_task(base_runs)
    cand_by_task = _group_by_task(candidate_runs)
    task_ids = sorted(set(base_by_task) & set(cand_by_task))

    pairs: list[TaskPair] = []
    for task_id in task_ids:
        b = base_by_task[task_id]
        c = cand_by_task[task_id]
        base_mean_v = _task_mean(b, task_id)
        cand_mean_v = _task_mean(c, task_id)
        pairs.append(
            TaskPair(
                task_id=task_id,
                base_mean=base_mean_v if base_mean_v is not None else 0.0,
                candidate_mean=cand_mean_v if cand_mean_v is not None else 0.0,
                base_passed=_task_passed(b, task_id),
                candidate_passed=_task_passed(c, task_id),
                base_n=len(b),
                candidate_n=len(c),
            )
        )

    base_scores = [p.base_mean for p in pairs]
    cand_scores = [p.candidate_mean for p in pairs]

    mean_delta = mean_paired_delta(base_scores, cand_scores)
    median_delta = median_paired_delta(base_scores, cand_scores)
    ci = paired_confidence_interval(
        base_scores, cand_scores, confidence=confidence, n_resamples=n_resamples, seed=seed
    )
    wins, ties, losses = win_tie_loss(base_scores, cand_scores)

    reg_list = detect_regressions(
        [p.task_id for p in pairs],
        base_scores,
        cand_scores,
        threshold=regress_threshold,
    )
    regressions = tuple(sorted((r for r in reg_list if r.regressed), key=lambda r: r.task_id))
    improvements = tuple(sorted((r for r in reg_list if r.improved), key=lambda r: r.task_id))

    transitions: dict[str, int] = {
        "pass_to_fail": 0,
        "fail_to_pass": 0,
        "stable_pass": 0,
        "stable_fail": 0,
    }
    for p in pairs:
        if p.base_passed is None or p.candidate_passed is None:
            continue
        if p.base_passed and p.candidate_passed:
            transitions["stable_pass"] += 1
        elif p.base_passed and not p.candidate_passed:
            transitions["pass_to_fail"] += 1
        elif not p.base_passed and p.candidate_passed:
            transitions["fail_to_pass"] += 1
        else:
            transitions["stable_fail"] += 1

    resource_keys = sorted(
        {k for r in base_runs for k in r.resources}
        & {k for r in candidate_runs for k in r.resources}
    )
    resource_deltas: list[ResourceDelta] = []
    for key in resource_keys:
        base_vals = [r.resources[key] for r in base_runs if key in r.resources]
        cand_vals = [r.resources[key] for r in candidate_runs if key in r.resources]
        if base_vals and cand_vals:
            resource_deltas.append(
                ResourceDelta(
                    resource=key,
                    mean_delta=mean(cand_vals) - mean(base_vals),
                    tasks=len(task_ids),
                )
            )

    return ComparisonResult(
        base_label=base_label,
        candidate_label=candidate_label,
        tasks=tuple(pairs),
        mean_delta=mean_delta,
        median_delta=median_delta,
        ci=ci,
        wins=wins,
        ties=ties,
        losses=losses,
        regressions=regressions,
        improvements=improvements,
        failure_transitions=transitions,
        resource_deltas=tuple(resource_deltas),
        significant=is_significant(ci, sample_size=len(pairs), min_samples=min_samples),
        sample_size=len(pairs),
    )

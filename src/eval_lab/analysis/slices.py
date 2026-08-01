"""Label slicing (spec 17.1, 8.1B, Phase 5)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from eval_lab.analysis.statistics import mean, weighted_mean
from eval_lab.analysis.weighted import SliceAggregate, TaskRow

__all__ = ["SliceAggregate", "TaskRow", "slice_dimensions", "slice_tasks"]


def slice_tasks(rows: Sequence[TaskRow], axis: str) -> dict[str, SliceAggregate]:
    """Group per-task rows by the values of a label dimension.

    Each task contributes to every label value it carries on ``axis`` (a
    multi-label task appears in several buckets). Both weighted (by suite task
    weight) and raw unweighted aggregates are reported per bucket.
    """
    buckets: dict[str, list[TaskRow]] = defaultdict(list)
    for row in rows:
        for value in row.labels.get(axis, frozenset()):
            buckets[value].append(row)

    out: dict[str, SliceAggregate] = {}
    for value in sorted(buckets):
        bucket = buckets[value]
        scored = [r for r in bucket if r.score is not None]
        passed = [r for r in bucket if r.passed is not None]
        scored_scores = [float(r.score) for r in scored if r.score is not None]
        scored_weights = [r.weight for r in scored]
        pass_flags = [1.0 if r.passed else 0.0 for r in passed]
        pass_weights = [r.weight for r in passed]
        out[value] = SliceAggregate(
            label=value,
            task_count=len(bucket),
            scored_tasks=len(scored),
            weighted_score=weighted_mean(scored_scores, scored_weights) if scored_scores else 0.0,
            unweighted_score=mean(scored_scores),
            weighted_pass_rate=weighted_mean(pass_flags, pass_weights) if pass_flags else 0.0,
            unweighted_pass_rate=mean(pass_flags),
        )
    return out


def slice_dimensions() -> list[str]:
    """Label axes available for slicing, mirroring the vocab DOMAINS of labels."""
    return ["domain", "capability", "modality", "trajectory_stage", "failure_mode", "difficulty"]

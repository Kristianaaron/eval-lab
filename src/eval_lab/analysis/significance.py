"""Significance interpretation for paired comparisons (spec 17.2, 17.3)."""

from __future__ import annotations

from collections.abc import Sequence

from eval_lab.analysis.statistics import bootstrap_ci, mean, median


def paired_deltas(base: Sequence[float], candidate: Sequence[float]) -> list[float]:
    """Per-pair ``candidate - base`` deltas (pairs matched by position)."""
    return [c - b for b, c in zip(base, candidate, strict=True)]


def win_tie_loss(
    base: Sequence[float],
    candidate: Sequence[float],
    *,
    epsilon: float = 0.0,
) -> tuple[int, int, int]:
    """Task-level wins/ties/losses for candidate vs base.

    Returns ``(candidate_wins, ties, candidate_losses)``. A pair is a win/loss
    only when it differs by more than ``epsilon``.
    """
    wins = ties = losses = 0
    for b, c in zip(base, candidate, strict=True):
        if c > b + epsilon:
            wins += 1
        elif c < b - epsilon:
            losses += 1
        else:
            ties += 1
    return wins, ties, losses


def mean_paired_delta(base: Sequence[float], candidate: Sequence[float]) -> float:
    deltas = paired_deltas(base, candidate)
    return mean(deltas)


def median_paired_delta(base: Sequence[float], candidate: Sequence[float]) -> float:
    deltas = paired_deltas(base, candidate)
    return median(deltas)


def paired_confidence_interval(
    base: Sequence[float],
    candidate: Sequence[float],
    *,
    confidence: float = 0.95,
    n_resamples: int = 2000,
    seed: int = 1234,
) -> tuple[float | None, float | None]:
    """Bootstrap CI on the mean paired delta.

    ``None`` bounds signal too few matched pairs to resample.
    """
    deltas = paired_deltas(base, candidate)
    if not deltas:
        return (None, None)
    low, high = bootstrap_ci(deltas, n_resamples=n_resamples, confidence=confidence, seed=seed)
    return (low, high)


def is_significant(
    ci: tuple[float | None, float | None],
    *,
    sample_size: int,
    min_samples: int = 3,
) -> bool:
    """True only when the CI excludes zero and the sample is large enough.

    Per spec 17.3, a wide interval or tiny sample must not be reported as
    superiority, so both conditions are required.
    """
    low, high = ci
    if sample_size < min_samples or low is None or high is None:
        return False
    return not (low <= 0.0 <= high)

"""Descriptive statistics and bootstrap confidence intervals (spec 17.3)."""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence

Statistic = Callable[[Sequence[float]], float]


def mean(values: Sequence[float]) -> float:
    """Arithmetic mean; 0.0 for an empty input."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def median(values: Sequence[float]) -> float:
    """Median; 0.0 for an empty input."""
    if not values:
        return 0.0
    xs = sorted(values)
    n = len(xs)
    mid = n // 2
    if n % 2:
        return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2.0


def quantile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated quantile for ``q`` in ``[0, 1]``."""
    if not values:
        return 0.0
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1.0 - frac) + xs[hi] * frac


def weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    """Weighted mean; 0.0 for empty/zero-weight inputs."""
    total_weight = sum(weights)
    if not values or total_weight <= 0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights, strict=False)) / total_weight


def bootstrap_ci(
    values: Sequence[float],
    stat: Statistic = mean,
    *,
    n_resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 1234,
) -> tuple[float, float]:
    """Percentile bootstrap confidence interval for ``stat`` over ``values``.

    Resamples with replacement (seeded for reproducibility) and returns the
    ``(low, high)`` interval spanning the requested confidence quantiles.
    Returns ``(nan, nan)`` when ``values`` is empty.
    """
    if not values:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(values)
    distribution: list[float] = []
    for _ in range(n_resamples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        distribution.append(stat(sample))
    alpha = (1.0 - confidence) / 2.0
    distribution.sort()
    return (quantile(distribution, alpha), quantile(distribution, 1.0 - alpha))

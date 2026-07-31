"""Pairwise comparison helpers: randomized A/B order with bias guards (spec 14.2)."""

from __future__ import annotations

import random
from typing import Any


def order[T](seed: int, a: T, b: T) -> tuple[T, T]:
    """Return (first, second) with the A/B order randomized by ``seed``.

    Deterministic for a given seed, so results are reproducible and the seed is
    recorded by the caller to audit ordering. Model identity never leaks into
    this function — the caller decides what ``a``/``b`` stand for.
    """
    if random.Random(seed).random() < 0.5:
        return (a, b)
    return (b, a)


def comparable(identity_a: Any, identity_b: Any) -> bool:
    """Self-preference guard: refuse to compare a model to itself."""
    return identity_a is not None and identity_a != identity_b


def order_bias_pp(judgements: list[dict[str, Any]]) -> float | None:
    """Order-bias in percentage points from pairwise judge judgements.

    Each item is ``{"first_preference": int, "second_preference": int}`` where
    the preference (1 -> first, 2 -> second, 0 -> tie) came from judging the
    pair in each order. Returns the fraction of pairs whose preference flips
    with presentation order, scaled to percentage points, or None when verdicts
    are ties in both orders or no comparable pairs exist.
    """
    flips = 0
    measured = 0
    for j in judgements:
        p1 = j.get("first_preference")
        p2 = j.get("second_preference")
        if p1 is None or p2 is None:
            continue
        if p1 == 0 and p2 == 0:
            continue
        measured += 1
        if p1 != p2:
            flips += 1
    if measured == 0:
        return None
    return round(flips / measured * 100.0, 2)

"""Backoff schedules for retrying sink writes."""

from __future__ import annotations

from collections.abc import Iterator


def exponential(base: float, factor: float, cap: float, attempts: int) -> Iterator[float]:
    if base <= 0 or factor < 1 or cap <= 0 or attempts < 0:
        raise ValueError("invalid backoff parameters")
    delay = base
    for _ in range(attempts):
        yield min(delay, cap)
        delay *= factor


def total_wait(base: float, factor: float, cap: float, attempts: int) -> float:
    return sum(exponential(base, factor, cap, attempts))


def with_jitter(delays: Iterator[float], fraction: float, seed: int = 0) -> Iterator[float]:
    """Deterministic jitter: each delay is scaled by 1 ± fraction using a LCG."""
    if not 0 <= fraction < 1:
        raise ValueError("fraction must be in [0, 1)")
    state = seed & 0xFFFFFFFF
    for d in delays:
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        unit = state / 0x7FFFFFFF
        yield d * (1 - fraction + 2 * fraction * unit)

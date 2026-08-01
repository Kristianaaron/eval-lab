"""Pareto frontier analysis (spec 17.4)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    """A configuration point: higher quality is better, lower resources are better."""

    label: str
    quality: float
    latency: float | None = None
    memory: float | None = None

    def dominates(self, other: Point) -> bool:
        """Strictly better on quality and no worse on every provided resource."""
        if self.quality < other.quality:
            return False
        for self_res, other_res in (
            (self.latency, other.latency),
            (self.memory, other.memory),
        ):
            if self_res is None or other_res is None:
                continue
            if self_res > other_res:
                return False
        # Strict domination: better somewhere, equal-or-better everywhere.
        return self._better_somewhere(other) and not self._equal_everywhere(other)

    def _better_somewhere(self, other: Point) -> bool:
        if self.quality > other.quality:
            return True
        for self_res, other_res in ((self.latency, other.latency), (self.memory, other.memory)):
            if self_res is not None and other_res is not None and self_res < other_res:
                return True
        return False

    def _equal_everywhere(self, other: Point) -> bool:
        if self.quality != other.quality:
            return False
        for self_res, other_res in ((self.latency, other.latency), (self.memory, other.memory)):
            if self_res is not None and other_res is not None and self_res != other_res:
                return False
        return True


def pareto_frontier(
    points: Sequence[Point],
    *,
    key: Callable[[Point], tuple[float, ...]] | None = None,
) -> list[Point]:
    """Return the subset of mutually non-dominated points (the frontier).

    A point is on the frontier when no other point dominates it. The frontier
    is returned sorted by quality ascending (then latency ascending).
    """
    frontier: list[Point] = []
    for p in points:
        dominated = any(q.dominates(p) for q in points if q.label != p.label)
        if not dominated:
            frontier.append(p)
    frontier.sort(key=key or (lambda p: (p.quality, p.latency if p.latency is not None else 0.0)))
    return frontier

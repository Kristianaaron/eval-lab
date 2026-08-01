"""Regression detection for before/after comparison (spec 17.2, 4.8)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Regression:
    """A single task-level score change between two configurations."""

    task_id: str
    base_score: float
    candidate_score: float
    threshold: float

    @property
    def delta(self) -> float:
        """Candidate minus base score change."""
        return self.candidate_score - self.base_score

    @property
    def regressed(self) -> bool:
        """Candidate meaningfully* worse than base (beyond threshold)."""
        return self.base_score - self.candidate_score > self.threshold

    @property
    def improved(self) -> bool:
        """Candidate meaningfully* better than base (beyond threshold)."""
        return self.candidate_score - self.base_score > self.threshold


def detect_regressions(
    task_ids: Sequence[str],
    base_scores: Sequence[float],
    candidate_scores: Sequence[float],
    *,
    threshold: float = 0.05,
) -> list[Regression]:
    """Pair each task and flag regressions/improvements beyond ``threshold``."""
    out: list[Regression] = []
    for task_id, base, cand in zip(task_ids, base_scores, candidate_scores, strict=True):
        out.append(Regression(task_id, base, cand, threshold))
    return out


def regressions(regressions: Iterable[Regression]) -> list[Regression]:
    return [r for r in regressions if r.regressed]


def improvements(regressions: Iterable[Regression]) -> list[Regression]:
    return [r for r in regressions if r.improved]

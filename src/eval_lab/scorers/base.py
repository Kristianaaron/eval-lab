"""Scorer protocol and registry (spec 13)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from eval_lab.schemas.models import ScoreResult


class Scorer(Protocol):
    scorer_id: str

    def score(self, *, output: str, task: Any, run_dir: Any | None = None) -> ScoreResult: ...


@dataclass
class ScoreContext:
    """Context passed to scorers that need workspace/artifacts."""

    workspace: Any = None
    run_dir: Any = None
    extra: dict[str, Any] = field(default_factory=dict)


_SCORERS: dict[str, type] = {}


def register_scorer(scorer_id: str, cls: type) -> None:
    _SCORERS[scorer_id] = cls


def get_scorer(scorer_id: str) -> type:
    if scorer_id not in _SCORERS:
        raise KeyError(f"unknown scorer: {scorer_id}")
    return _SCORERS[scorer_id]


def available_scorers() -> list[str]:
    return sorted(_SCORERS)

"""Score aggregation: weighted mean with required-failure gating (spec 13.1, 4.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Import registers deterministic scorers (exact/regex/json_schema).
import eval_lab.scorers.deterministic  # noqa: F401  (side-effect registration)
from eval_lab.schemas.models import ScoreResult, TaskSpec
from eval_lab.scorers.base import Scorer, get_scorer


@dataclass
class AggregateScore:
    total: float
    passed: bool
    weight_sum: float
    scores: list[ScoreResult] = field(default_factory=list)
    required_failures: list[str] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict, repr=False)


def aggregate(
    scores: list[ScoreResult],
    *,
    required_by_id: dict[str, bool] | None = None,
    weights: dict[str, float] | None = None,
) -> AggregateScore:
    """Weighted mean of scores; any required scorer failure fails the aggregate.

    ``weights`` maps scorer_id -> weight (default 1.0). A required failure
    forces ``passed=False`` regardless of the weighted mean. Scorers that error
    do not silently become zeros; they are excluded and recorded.
    """
    required_by_id = required_by_id or {}
    weights = weights or {}
    weight_sum = 0.0
    weighted_sum = 0.0
    required_failures: list[str] = []
    errored: list[str] = []

    for sc in scores:
        w = float(weights.get(sc.scorer_id, 1.0))
        required = required_by_id.get(sc.scorer_id, sc.required)
        if required and not sc.passed:
            required_failures.append(sc.scorer_id)
        if sc.error:
            errored.append(sc.scorer_id)
            continue
        weighted_sum += sc.score * w
        weight_sum += w

    total = weighted_sum / weight_sum if weight_sum else 0.0
    passed = not required_failures and weight_sum > 0
    return AggregateScore(
        total=total,
        passed=passed,
        weight_sum=weight_sum,
        scores=scores,
        required_failures=required_failures,
        weights=weights,
    )


def score_oracle(
    task: TaskSpec,
    *,
    output: str,
    run_dir: Any = None,
    required_map: dict[str, bool] | None = None,
) -> AggregateScore:
    """Run every oracle scorer ref on a task against ``output``."""
    scores: list[ScoreResult] = []
    weight_map: dict[str, float] = {}
    req: dict[str, bool] = dict(required_map or {})
    for ref in task.oracle:
        cls = get_scorer(ref.type)
        inst = _instantiate(cls, ref.config)
        result = inst.score(output=output, task=task, run_dir=run_dir)
        result.required = bool(ref.required)
        weight_map[ref.type] = float(ref.weight)
        req[ref.type] = bool(ref.required)
        scores.append(result)
    return aggregate(scores, required_by_id=req, weights=weight_map)


def _instantiate(cls: type[Scorer], config: dict[str, Any]) -> Scorer:
    try:
        return cls(**config)
    except TypeError:
        return cls()

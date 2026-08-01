"""Alternative weighting scenarios for composite recomputation (spec 17.4)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from eval_lab.analysis.weighted import TaskRow


@dataclass(frozen=True)
class WeightingScenario:
    """A versioned reweighting: per-domain multipliers over the suite weights."""

    id: str
    name: str
    domain_weights: dict[str, float]
    regress_threshold: float = 0.05
    schema_version: str = "1.0"


def load_weighting_scenario(path: str | Path) -> WeightingScenario:
    """Load a weighting-scenario YAML (configs/reports/*.yaml)."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    domains = data.get("domain_weights") or {}
    return WeightingScenario(
        id=str(data.get("id", Path(path).stem)),
        name=str(data.get("name", Path(path).stem)),
        domain_weights={str(k): float(v) for k, v in domains.items()},
        regress_threshold=float(data.get("regress_threshold", 0.05)),
        schema_version=str(data.get("schema_version", "1.0")),
    )


def reweight_tasks(rows: list[TaskRow], scenario: WeightingScenario) -> list[TaskRow]:
    """Scale each task's suite weight by its domain multipliers in the scenario.

    A task carrying several domains gets the product of the multipliers.
    """
    out: list[TaskRow] = []
    for row in rows:
        factor = 1.0
        for domain in row.labels.get("domain", frozenset()):
            factor *= scenario.domain_weights.get(domain, 1.0)
        out.append(
            TaskRow(
                task_id=row.task_id,
                weight=row.weight * factor,
                score=row.score,
                passed=row.passed,
                duration_s=row.duration_s,
                labels=row.labels,
                n_runs=row.n_runs,
            )
        )
    return out

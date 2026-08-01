"""Suite and comparison analysis (Phase 5)."""

from __future__ import annotations

from eval_lab.analysis.comparison import (
    ComparisonResult,
    ResourceDelta,
    TaskPair,
    compare_groups,
)
from eval_lab.analysis.pareto import Point, pareto_frontier
from eval_lab.analysis.regression import Regression, detect_regressions
from eval_lab.analysis.rows import RunRow, load_run_rows
from eval_lab.analysis.significance import is_significant, paired_confidence_interval
from eval_lab.analysis.slices import SliceAggregate, slice_dimensions, slice_tasks
from eval_lab.analysis.statistics import bootstrap_ci, mean, median, quantile, weighted_mean
from eval_lab.analysis.weighted import (
    SuiteAggregate,
    TaskRow,
    aggregate_suite,
    aggregate_task_rows,
    build_task_rows,
)

__all__ = [
    "ComparisonResult",
    "Point",
    "Regression",
    "ResourceDelta",
    "RunRow",
    "SliceAggregate",
    "SuiteAggregate",
    "TaskPair",
    "TaskRow",
    "aggregate_suite",
    "aggregate_task_rows",
    "bootstrap_ci",
    "build_task_rows",
    "compare_groups",
    "detect_regressions",
    "is_significant",
    "load_run_rows",
    "mean",
    "median",
    "paired_confidence_interval",
    "pareto_frontier",
    "quantile",
    "slice_dimensions",
    "slice_tasks",
    "weighted_mean",
]

"""Calibration vs held-out leakage guard (spec 4, 15.5, correction #2).

Task ``data_partition`` marks atlas-calibration tasks; an evaluation that runs
those tasks as if they were held-out is biased. This service detects overlap so
the GUI can warn and block promotion-style reports by default.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from eval_lab.schemas.models import TaskSpec

CALIBRATION_PARTITION = "atlas_calibration"
HELD_OUT_PARTITION = "held_out_evaluation"


@dataclass(frozen=True)
class LeakageResult:
    overlapping_task_ids: list[str] = field(default_factory=list)
    blocked: bool = False
    message: str | None = None

    @property
    def detected(self) -> bool:
        return bool(self.overlapping_task_ids)


def calibration_task_ids(tasks: Iterable[TaskSpec]) -> set[str]:
    """Task ids used for atlas calibration (calibration partition only)."""
    return {t.id for t in tasks if t.data_partition == CALIBRATION_PARTITION}


def check_leakage(
    eval_tasks: Iterable[TaskSpec],
    calibration_ids: set[str] | None = None,
    *,
    held_out: bool = True,
) -> LeakageResult:
    """Detect overlap between an evaluation suite and the calibration set."""
    if calibration_ids is None:
        calibration_ids = calibration_task_ids(eval_tasks)
    overlap = sorted({t.id for t in eval_tasks if t.id in calibration_ids})
    if not overlap:
        return LeakageResult()
    message = (
        "This suite contains tasks used to construct the selected atlas. Results "
        "may be biased and cannot be treated as held-out evidence."
    )
    return LeakageResult(
        overlapping_task_ids=overlap,
        blocked=held_out,
        message=message,
    )

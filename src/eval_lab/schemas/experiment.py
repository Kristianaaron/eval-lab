"""Typed schemas for experiments (Milestone 5, blueprint §Experiment).

An experiment is a saved, evaluable intervention strategy derived from an
imported atlas run: it pins one candidate plan (keep-map / precision /
residency) from ``plans.json`` as a named objective, preserving source identity
via the keep-map and linking any derivative model asset built from that run.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ExperimentType(StrEnum):
    keep_map = "keep_map"
    precision = "precision"
    residency = "residency"


class ExperimentStatus(StrEnum):
    draft = "draft"
    active = "active"
    completed = "completed"
    superseded = "superseded"


class ExperimentRecord(BaseModel):
    """One saved experiment, pinned to an imported atlas run + candidate plan."""

    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    experiment_type: ExperimentType = ExperimentType.keep_map
    run_id: str  # source atlas run (atlas-bridge import)
    plan_name: str  # candidate plan name from plans.json
    objective: str = ""
    memory_target_bytes: int | None = None
    kept_per_layer: dict[str, int] = Field(default_factory=dict)
    total_kept: int = 0
    derivate_asset_id: str | None = None
    source_asset_id: str | None = None
    status: ExperimentStatus = ExperimentStatus.draft
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

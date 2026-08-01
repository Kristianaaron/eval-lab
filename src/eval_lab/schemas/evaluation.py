"""Evaluation-run configuration + evaluation job schemas (correction #3, M2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvaluationConfig(BaseModel):
    """Everything recorded for one evaluation run (spec 2.3 — identity is explicit)."""

    model_config = ConfigDict(extra="forbid")

    model_asset_id: str
    model_id: str
    harness_id: str | None = None
    suite_ref: str  # suite YAML path or id
    label_filters: list[str] = Field(default_factory=list)
    repeat_count: int = Field(default=1, ge=1)
    cold_start: bool = False
    sampling: dict[str, Any] = Field(default_factory=dict)
    telemetry_interval_s: float | None = None
    runs_root: str = "runs"

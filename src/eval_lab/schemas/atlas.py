"""Reserved atlas schemas (correction #5; no atlas runtime yet).

These establish the contracts that the future Atlas Lab subsystem must satisfy
without coupling to the evaluation runner: evidence levels, the measured-vs-
inferred distinction, source↔derivative expert identity, and per-trace linkage
to task/behaviour labels. Nothing here executes; it is the data shape the atlas
artifacts will adopt.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvidenceLevel(StrEnum):
    """Analysis depth (spec 6): Basic = correlation, not causation."""

    basic_saliency = "basic_saliency"
    enhanced_atlas = "enhanced_atlas"
    causal_atlas = "causal_atlas"


class EvidenceKind(StrEnum):
    """How a claim was produced; correlation is never presented as causation."""

    measured = "measured"
    estimated = "estimated"
    predicted = "predicted"
    inferred = "inferred"
    causally_tested = "causally_tested"


class ExpertIdentity(BaseModel):
    """Stable expert identity; source id is never overwritten by derivative renumbering."""

    source_model_id: str
    layer_index: int
    source_expert_id: int
    derivative_model_id: str | None = None
    derivative_expert_id: int | None = None
    keep_map_id: str | None = None


class AtlasTraceField(BaseModel):
    """One routed/moe signal linked to labelled behaviour (spec 8)."""

    model_config = ConfigDict(extra="forbid")

    atlas_run_id: str
    task_id: str | None = None
    sample_id: str | None = None
    capability_labels: list[str] = Field(default_factory=list)
    trajectory_stage: str | None = None
    token_range: tuple[int, int] | None = None
    expert: ExpertIdentity
    trace_type: str  # e.g. router_probability, activation_count, output_norm, router_weighted_norm
    trace_value: float
    evidence_kind: EvidenceKind = EvidenceKind.measured
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class AtlasRunManifest(BaseModel):
    atlas_run_id: str
    source_checkpoint_id: str
    calibration_suite_id: str
    evidence_level: EvidenceLevel = EvidenceLevel.basic_saliency
    # Which artifact files are present under atlas_runs/<id>/ (spec 7).
    evidence_present: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    software_revision: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

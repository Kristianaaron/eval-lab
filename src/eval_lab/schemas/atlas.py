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


class UnitKind(StrEnum):
    """What kind of routed/kept unit a keep-map or saliency refers to.

    Atlas today records expert routing; attention heads are the same dissection
    applied to the per-block attention axis (top-k head selection).
    """

    expert = "expert"
    head = "head"


class UnitIdentity(BaseModel):
    """Stable identity for any kept/measured unit (routed expert or attention
    head). Source id is never overwritten by derivative renumbering, so a
    top-8 head in a derivative always traces to the same source head as the
    top-4 selection that preceded it.

    ``unit_kind`` discriminates experts (default) from heads; a head shares
    the same per-layer index space as an expert, so the kind must be explicit.
    """

    source_model_id: str
    layer_index: int
    unit_kind: UnitKind = UnitKind.expert
    source_unit_id: int
    derivative_model_id: str | None = None
    derivative_unit_id: int | None = None
    keep_map_id: str | None = None


class KeepMapEntry(BaseModel):
    """One unit's entry in a keep-map: identity plus the saliency that justified
    keeping or dropping it, so a prune topology is auditable per unit.
    """

    model_config = ConfigDict(extra="forbid")

    unit: UnitIdentity
    kept: bool
    top_k: int  # 0 = full (no routing restriction)
    saliency: float | None = Field(default=None, ge=0.0)
    saliency_signal: str | None = None  # activation_count | output_norm | router_probability | ...
    evidence_kind: EvidenceKind = EvidenceKind.measured
    rank_within_layer: int | None = Field(default=None, ge=1)


class UnitKeepMap(BaseModel):
    """A keep-map for one layer: the per-layer top-k selection of heads/experts.
    ``top_k`` is the routing budget for this layer; ``entries`` carry each unit's
    keep decision and its measured saliency.
    """

    model_config = ConfigDict(extra="forbid")

    layer_index: int
    unit_kind: UnitKind
    top_k: int
    entries: list[KeepMapEntry] = Field(default_factory=list)

    @property
    def kept_count(self) -> int:
        return sum(1 for e in self.entries if e.kept)


class AtlasTraceField(BaseModel):
    """One routed/moe signal linked to labelled behaviour (spec 8)."""

    model_config = ConfigDict(extra="forbid")

    atlas_run_id: str
    task_id: str | None = None
    sample_id: str | None = None
    capability_labels: list[str] = Field(default_factory=list)
    trajectory_stage: str | None = None
    token_range: tuple[int, int] | None = None
    unit: UnitIdentity
    # e.g. router_probability, activation_count, output_norm, head_activation
    trace_type: str
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

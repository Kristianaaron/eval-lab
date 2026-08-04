"""Atlas Lab runtime (Milestone 3) — build-atlas configuration and run DTOs.

The M3 runtime is eval-lab's own lightweight layerwise MoE tracer: it constructs
a small deterministic synthetic MoE (config.json + weights), runs a genuine
CPU router/expert forward pass over deterministic calibration contexts, and
measures real per-layer/per-expert saliency that is persisted as the reserved
atlas artifacts (``atlas_runs/<id>/``) and imported through the atlas-bridge
consumer. These schemas are the wizard's configuration surface and the run
detail the GUI renders; the on-disk artifact shape reuses ``schemas/atlas.py``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from eval_lab.schemas.atlas import UnitKeepMap


class TraceDepth(StrEnum):
    """How many calibration contexts the tracer processes (pacing knob)."""

    smoke = "smoke"
    basic = "basic"
    full = "full"


TRACE_DEPTH_PARAMS: dict[TraceDepth, tuple[int, int]] = {
    TraceDepth.smoke: (8, 8),  # (num_samples, seq_len)
    TraceDepth.basic: (24, 16),
    TraceDepth.full: (96, 24),
}

DEFAULT_MINI_MOE = {
    "num_hidden_layers": 6,
    "num_local_experts": 8,
    "num_experts_per_tok": 2,
    "hidden_size": 32,
    "intermediate_size": 64,
    "seed": 0,
}

DEFAULT_KEEP_BUDGETS = [8, 6, 4, 2]  # top-k per layer to evaluate as candidate plans


class AtlasBuildConfig(BaseModel):
    """Everything recorded for one build-atlas job (the M3 wizard config)."""

    model_config = ConfigDict(extra="forbid")

    model_asset_id: str
    suite_ref: str  # calibration suite path or id (provenance + n_tasks + labels)
    trace_depth: TraceDepth = TraceDepth.basic
    # Synthetic mini-MoE topology overrides (defaults used when None).
    num_hidden_layers: int | None = Field(default=None, ge=1)
    num_local_experts: int | None = Field(default=None, ge=1)
    num_experts_per_tok: int | None = Field(default=None, ge=1)
    hidden_size: int | None = Field(default=None, ge=4)
    intermediate_size: int | None = Field(default=None, ge=4)
    seed: int = 0
    capability_labels: list[str] = Field(default_factory=list)
    keep_budgets: list[int] | None = None  # candidate keep-k plans, clamped to experts
    runs_root: str = "runs"  # retained; atlas runs always live under atlas_out/atlas_runs


class ResourceEstimate(BaseModel):
    """Honest estimate of the tracer's compute envelope (labelled estimated)."""

    model_config = ConfigDict(extra="forbid")

    num_layers: int
    num_experts: int
    top_k: int
    num_samples: int
    seq_len: int
    num_tokens: int
    estimated_ops: float
    estimated_wall_s: float
    mini_moe_params: int
    mini_moe_resident_bytes: int
    trace_bytes: int
    methodology: str


class AtlasPlanPreview(BaseModel):
    """One candidate keep-map plan computed from measured saliency."""

    model_config = ConfigDict(extra="forbid")

    name: str
    strategy: str
    keep_per_layer: int
    kept_per_layer: dict[str, int]
    resident_bytes_a: float  # estimated kept params, full precision
    resident_bytes_b: float  # estimated kept params, half precision


class SqlRow(BaseModel):
    """One aggregate saliency row for a routed expert in a layer."""

    model_config = ConfigDict(extra="forbid")

    layer: int
    expert: int
    mean: float
    frequency: float
    total_value: float
    variance: float
    activation_count: int
    n_routed: int


class AtlasRunDetail(BaseModel):
    """The M3 GUI run-detail payload (real artifacts, not the bridge record)."""

    model_config = ConfigDict(extra="forbid")

    atlas_run_id: str
    source_checkpoint_id: str
    calibration_suite_id: str
    status: str
    evidence_level: str
    evidence_present: list[str]
    n_tasks: int
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    source_arch: str | None = None
    topology: dict[str, Any] = Field(default_factory=dict)
    plans: list[AtlasPlanPreview] = Field(default_factory=list)
    keep_maps: list[UnitKeepMap] = Field(default_factory=list)
    saliency: list[SqlRow] = Field(default_factory=list)
    saliency_by_label: list[dict[str, Any]] = Field(default_factory=list)
    trace_count: int = 0
    software_revision: str | None = None

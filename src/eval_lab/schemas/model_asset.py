"""Typed schemas for model assets, checkpoint inspection and action eligibility.

These are the application-facing contracts the GUI and service layer share.
View components never touch persistence or checkpoint internals directly; they
consume ``resolve_available_actions`` results and inspection records (spec 3.4,
3.3, 11).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ModelAssetType(StrEnum):
    source_checkpoint = "source_checkpoint"
    runnable_local = "runnable_local"
    derivative_checkpoint = "derivative_checkpoint"
    remote_endpoint = "remote_endpoint"
    hosted_teacher = "hosted_teacher"
    draft = "draft"
    multimodal_component = "multimodal_component"


class ValidationState(StrEnum):
    unvalidated = "unvalidated"
    valid = "valid"
    invalid = "invalid"


class ModelAssetRecord(BaseModel):
    """A registered model asset (spec 2.2). Independent of any run or atlas."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str
    asset_type: ModelAssetType
    path: str | None = None
    family: str | None = None
    architecture: str | None = None
    revision: str | None = None
    quantization_format: str | None = None
    param_metadata: dict[str, Any] = Field(default_factory=dict)
    stored_size_bytes: int | None = None
    resident_estimate_bytes: int | None = None
    runnable: bool = False
    atlas_compatible: bool = False
    validation_state: ValidationState = ValidationState.unvalidated
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    parent_asset_id: str | None = None
    source_experiment_id: str | None = None
    source_atlas_run_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    last_atlas_run_id: str | None = None
    latest_quality_score: float | None = None
    latest_eval_run_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    precision_roles: list[dict[str, object]] = Field(
        default_factory=list,
        description="per-role achieved bits/weight from the header census",
    )


class InspectionIssue(BaseModel):
    level: str = Field(pattern="^(info|warning|error)$")
    message: str


class CheckpointInspection(BaseModel):
    """Lightweight path inspection: headers read, tensor payloads never loaded."""

    model_config = ConfigDict(extra="forbid")

    path: str
    valid: bool
    model_type: str | None = None
    architecture: str | None = None
    num_hidden_layers: int | None = None
    num_local_experts: int | None = None
    num_experts_per_tok: int | None = None
    quantization_format: str | None = None
    tensor_dtype: str | None = None
    file_count: int = 0
    shard_count: int = 0
    stored_size_bytes: int = 0
    params_estimate: int | None = None
    resident_estimate_bytes: int | None = None
    runnable_here: bool = False
    atlas_compatible: bool = False
    node_access: bool = True
    inspected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    issues: list[InspectionIssue] = Field(default_factory=list)
    precision_roles: list[dict[str, object]] = Field(
        default_factory=list,
        description="per-role achieved bits/weight + stored bytes from headers",
    )


class AvailableAction(BaseModel):
    available: bool
    reason: str | None = None


class ActionEligibility(BaseModel):
    asset_id: str
    actions: dict[str, AvailableAction]


class EnvBudget(BaseModel):
    """Resident-memory/storage envelope used to resolve action eligibility."""

    available_unified_memory_gb: float = 256.0
    reserved_system_gb: float = 0.0
    resident_target_gb: float | None = None
    has_completed_atlas: bool = False
    has_completed_eval: bool = False


class InspectPathRequest(BaseModel):
    """Body for a mid-wizard inspection (no registration)."""

    path: str
    memory_gb: float = 256.0


class RegisterRequest(BaseModel):
    """Body for registering a local checkpoint directory."""

    path: str
    name: str | None = None
    asset_id: str | None = None
    memory_gb: float = 256.0


class InspectResult(BaseModel):
    inspection: CheckpointInspection
    recommend_atlas: bool


class RegisterResult(BaseModel):
    record: ModelAssetRecord
    inspection: CheckpointInspection
    actions: ActionEligibility

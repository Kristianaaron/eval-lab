"""Versioned core data contracts for eval-lab.

Every persisted object carries a ``schema_version`` and refuses unknown
required fields. These Pydantic models are the single source of truth for
tasks, suites, model configs, harness configs, run manifests, scores, and
trace events (spec 6).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eval_lab.config.labels import (
    validate,
    validate_many,
)

SCHEMA_VERSION = "1.0"


class EvalBase(BaseModel):
    """Base model: require exact fields (forbid unknown), force rigor."""

    model_config = ConfigDict(extra="forbid", frozen=False)

    schema_version: str = SCHEMA_VERSION


class Level(StrEnum):
    model = "model"
    system = "system"


class Status(StrEnum):
    active = "active"
    draft = "draft"
    deprecated = "deprecated"


# ---------------------------------------------------------------------------
# Task specification (spec 6.1)
# ---------------------------------------------------------------------------


class InputSpec(EvalBase):
    instruction_file: str = Field(description="path relative to the task package")
    attachments: list[str] = Field(default_factory=list)
    workspace_fixture: str | None = None
    initial_state_hash: str | None = Field(
        default=None, description="sha256:... of the initial workspace state"
    )


class ExecutionSpec(EvalBase):
    runner: Literal["direct", "agent"] = "agent"
    sandbox: str | None = None
    image: str | None = None
    network: Literal["enabled", "disabled"] = "disabled"
    timeout_seconds: int = Field(default=300, ge=1)
    max_turns: int | None = Field(default=None, ge=1)
    max_tool_calls: int | None = Field(default=None, ge=0)
    token_budget: int | None = Field(default=None, ge=1)
    allowed_tools: list[str] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    seeds: list[int] = Field(default_factory=list)


class ScorerRef(EvalBase):
    type: str
    weight: float = Field(default=1.0, ge=0.0)
    required: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class ArtifactRef(EvalBase):
    type: str
    path: str | None = None


class Repetitions(EvalBase):
    default: int = Field(default=1, ge=1)
    seeds: list[int] = Field(default_factory=list)


class TaskLabels(EvalBase):
    domains: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    modalities: list[str] = Field(default_factory=list)
    difficulty: str = "medium"
    trajectory_stages: list[str] = Field(default_factory=list)
    failure_modes_targeted: list[str] = Field(default_factory=list)
    intervention: list[str] = Field(default_factory=list)
    atlas_labels: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_vocabs(self) -> TaskLabels:
        for vocab, values in (
            ("domain", self.domains),
            ("capability", self.capabilities),
            ("modality", self.modalities),
            ("trajectory_stage", self.trajectory_stages),
            ("failure_mode", self.failure_modes_targeted),
            ("intervention", self.intervention),
        ):
            validate_many(vocab, values)
        validate("difficulty", self.difficulty)
        return self


class TaskSpec(EvalBase):
    """A single evaluation task (spec 6.1)."""

    id: str = Field(pattern=r"^[a-z0-9]+(\.[a-z0-9_-]+)+$")
    name: str
    description: str
    version: int = Field(default=1, ge=1)
    level: Level = Level.system
    status: Status = Status.active

    labels: TaskLabels = Field(default_factory=TaskLabels)
    # Spec 4: tasks are partitioned so atlas-calibration data is never reused as
    # held-out evaluation evidence. "unset" means no partition assigned yet.
    data_partition: Literal[
        "atlas_calibration", "development_evaluation", "held_out_evaluation", "unset"
    ] = "unset"
    input: InputSpec
    execution: ExecutionSpec = Field(default_factory=ExecutionSpec)
    oracle: list[ScorerRef] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    repetitions: Repetitions = Field(default_factory=Repetitions)


# ---------------------------------------------------------------------------
# Suite specification (spec 8)
# ---------------------------------------------------------------------------


class SuiteTaskRef(EvalBase):
    task_id: str
    weight: float = Field(default=1.0, ge=0.0)
    repetitions: int | None = None


class SuiteSpec(EvalBase):
    id: str = Field(pattern=r"^[a-z0-9]+(\.[a-z0-9_-]+)+$")
    name: str
    description: str = ""
    version: int = Field(default=1, ge=1)
    family: str | None = None
    tasks: list[SuiteTaskRef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Model configuration (spec 6.2)
# ---------------------------------------------------------------------------


class CheckpointRef(EvalBase):
    source: Literal["local", "huggingface", "remote"] = "local"
    path: str
    revision: str | None = None


class QuantizationRef(EvalBase):
    format: str | None = None
    details: str | None = None


class RuntimeRef(EvalBase):
    name: str
    version: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)


class SamplingDefaults(EvalBase):
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 4096


class Capabilities(EvalBase):
    chat: bool = True
    images: bool = False
    tools: bool = True


class ModelConfig(EvalBase):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    provider_type: str = "openai_compatible"
    endpoint: str | None = None
    model_name: str
    checkpoint: CheckpointRef | None = None
    quantization: QuantizationRef = Field(default_factory=QuantizationRef)
    runtime: RuntimeRef | None = None
    sampling_defaults: SamplingDefaults = Field(default_factory=SamplingDefaults)
    capabilities: Capabilities = Field(default_factory=Capabilities)


# ---------------------------------------------------------------------------
# Harness configuration (spec 6.3)
# ---------------------------------------------------------------------------


class ContextPolicy(EvalBase):
    strategy: str = "rolling_summary_plus_recent"
    max_context_tokens: int | None = Field(default=None, ge=1)
    retain_tool_outputs: Literal["all", "selective", "none"] = "selective"


class RecoveryPolicy(EvalBase):
    max_retries_per_tool: int = Field(default=0, ge=0)
    require_error_inspection: bool = False


class CompletionContract(EvalBase):
    require_final_summary: bool = False
    require_verification_evidence: bool = False


class HarnessConfig(EvalBase):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    agent_loop: str = "react_tool_feedback"
    system_prompt_file: str | None = None
    workspace_policy: str = "isolated_copy"
    context_policy: ContextPolicy = Field(default_factory=ContextPolicy)
    recovery_policy: RecoveryPolicy = Field(default_factory=RecoveryPolicy)
    completion_contract: CompletionContract = Field(default_factory=CompletionContract)
    tool_adapter_version: str = "1.0.0"


# ---------------------------------------------------------------------------
# Run manifest (spec 6.4)
# ---------------------------------------------------------------------------


class RunManifest(EvalBase):
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    git_commit: str | None = None
    dirty_state_hash: str | None = None
    task_id: str
    task_version: int
    suite_id: str | None = None
    suite_version: int | None = None
    model_id: str | None = None
    checkpoint_path: str | None = None
    quantization_format: str | None = None
    runtime: str | None = None
    runtime_arguments: dict[str, Any] = Field(default_factory=dict)
    harness_id: str | None = None
    random_seed: int | None = None
    sampling: dict[str, Any] = Field(default_factory=dict)
    budgets: dict[str, Any] = Field(default_factory=dict)
    warm_state: str | None = None
    telemetry_stream: str | None = None
    timing: dict[str, Any] = Field(default_factory=dict)
    repetition_index: int | None = None
    result_status: str | None = None


# ---------------------------------------------------------------------------
# Score result (spec 13.1)
# ---------------------------------------------------------------------------


class ScoreResult(EvalBase):
    scorer_id: str
    score: float = 0.0
    passed: bool = False
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    required: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    evidence_artifacts: list[str] = Field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
# Trace event (spec 6.5)
# ---------------------------------------------------------------------------


class TraceEvent(EvalBase):
    run_id: str
    sequence: int = Field(ge=0)
    time_monotonic_ns: int = Field(ge=0)
    event_type: str
    span_id: str | None = None
    parent_span_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

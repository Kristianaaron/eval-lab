"""Controlled vocabularies for task and run labels.

Labels are first-class data, not free-form tags (spec 4.3, 7). Every label used
in a task or suite must belong to a validated, versioned registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LABEL_SCHEMA_VERSION = "1.0"

_DOMAINS = {
    "coding",
    "software_engineering",
    "frontend",
    "visual_design",
    "voxel",
    "spatial_3d",
    "agentic",
    "tool_calling",
    "mathematics",
    "formal_reasoning",
    "general_reasoning",
    "research",
    "long_context",
    "multimodal",
    "creative_writing",
    "product_thinking",
    "knowledge_work",
}

_CAPABILITIES = {
    "instruction_following",
    "decomposition",
    "planning",
    "repository_navigation",
    "code_generation",
    "code_editing",
    "debugging",
    "test_generation",
    "test_execution",
    "error_interpretation",
    "failure_recovery",
    "tool_selection",
    "tool_argument_construction",
    "tool_result_grounding",
    "state_tracking",
    "long_horizon_coherence",
    "long_context_retrieval",
    "visual_grounding",
    "screenshot_to_code",
    "layout_fidelity",
    "interaction_design",
    "spatial_reasoning",
    "voxel_construction",
    "mathematical_reasoning",
    "proof_or_derivation",
    "creative_generation",
    "self_verification",
    "uncertainty_calibration",
}

_MODALITIES = {"text", "code", "image", "audio", "video", "structured"}

_DIFFICULTY = {"trivial", "easy", "medium", "hard", "expert"}

_LEVELS = {"model", "system"}

_FAILURE_MODES = {
    "invalid_output_format",
    "hallucinated_tool_result",
    "wrong_tool",
    "malformed_tool_arguments",
    "ignores_observation",
    "repeats_failed_action",
    "premature_completion",
    "fails_to_verify",
    "edits_wrong_file",
    "excessive_scope",
    "destructive_action",
    "loses_constraints",
    "context_forgetting",
    "planning_without_execution",
    "execution_without_plan",
    "plausible_but_unverified",
    "visual_mismatch",
    "spatial_inconsistency",
    "timeout",
    "out_of_memory",
    "model_server_error",
    "harness_error",
    "judge_error",
}

_INTERVENTIONS = {
    "baseline",
    "quantization",
    "mixed_precision",
    "expert_pruning",
    "graded_expert_bank",
    "router_repair",
    "residual_distillation",
    "logit_distillation",
    "hidden_state_distillation",
    "speculative_decoding",
    "expert_paging",
    "expert_prefetch",
    "tensor_parallel",
    "pipeline_parallel",
    "expert_parallel",
    "runtime_kernel_change",
}

_TRAJECTORY_STAGES = {"inspect", "plan", "modify", "execute", "verify"}


@dataclass(frozen=True)
class Vocab:
    """A named controlled vocabulary with optional aliases."""

    name: str
    allowed: frozenset[str]
    aliases: dict[str, str] = field(default_factory=dict)

    def canonical(self, value: str) -> str | None:
        """Return the canonical spelling for a value, or None if unknown."""
        if value in self.allowed:
            return value
        key = value.strip().replace("_", "-").lower()
        # Case- and separator-insensitive match against the vocabulary itself.
        for label in self.allowed:
            if label.replace("_", "-").lower() == key:
                return label
        return self.aliases.get(key)


VOCABS: dict[str, Vocab] = {
    "domain": Vocab(
        "domain",
        frozenset(_DOMAINS),
        {"sw-eng": "software_engineering", "soft-eng": "software_engineering"},
    ),
    "capability": Vocab("capability", frozenset(_CAPABILITIES)),
    "modality": Vocab("modality", frozenset(_MODALITIES)),
    "difficulty": Vocab("difficulty", frozenset(_DIFFICULTY)),
    "level": Vocab("level", frozenset(_LEVELS)),
    "failure_mode": Vocab("failure_mode", frozenset(_FAILURE_MODES)),
    "intervention": Vocab("intervention", frozenset(_INTERVENTIONS)),
    "trajectory_stage": Vocab("trajectory_stage", frozenset(_TRAJECTORY_STAGES)),
}


class LabelError(ValueError):
    """Raised when a label does not belong to its controlled vocabulary."""


def canonical(vocab: str, value: str) -> str:
    """Resolve ``value`` within ``vocab`` to its canonical spelling."""
    return VOCABS[vocab].canonical(value) or value


def validate(vocab: str, value: str) -> str:
    """Validate one label; raises LabelError on an unknown value."""
    if vocab not in VOCABS:
        raise LabelError(f"unknown label vocabulary: {vocab}")
    canonical_value = VOCABS[vocab].canonical(value)
    if canonical_value is None:
        raise LabelError(f"'{value}' is not a valid {vocab} label")
    return canonical_value


def validate_many(vocab: str, values: list[str]) -> list[str]:
    return [validate(vocab, v) for v in values]


def unknown(vocab: str, values: list[str]) -> list[str]:
    """Return the labels in ``values`` that are not valid in ``vocab``."""
    bad: list[str] = []
    for v in values:
        try:
            validate(vocab, v)
        except LabelError:
            bad.append(v)
    return bad


def all_in(vocab: str) -> list[str]:
    return sorted(VOCABS[vocab].allowed)

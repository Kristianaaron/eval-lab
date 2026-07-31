"""Judge protocol, strict output model, and judge config schema (spec 14)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, ValidationError

# ---------------------------------------------------------------------------
# Strictly validated structured output (everything an LLM judge may emit).
# The model is parsed with extra="forbid" so unexpected fields are malformed.
# ---------------------------------------------------------------------------


class JudgeEmission(BaseModel):
    """The exact JSON a judge must emit; unknown fields are rejected."""

    model_config = {"extra": "forbid"}

    dimension: str
    score: float = Field(ge=0.0, le=1.0)
    label_level: int = Field(ge=0)
    label: str
    rational: str | None = None
    aspects: dict[str, float] = Field(default_factory=dict)


def parse_judge_json(text: str) -> JudgeEmission:
    """Strictly parse and validate a judge's structured JSON output.

    Raises ``ValueError`` on any malformed output (invalid JSON, missing
    fields, out-of-range score, unknown keys, wrong types) so callers can count
    it toward the malformed-output rate rather than silently accepting it.
    """
    if not text or not text.strip():
        raise ValueError("empty judge output")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("judge output must be a JSON object")
    try:
        return JudgeEmission.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"schema validation failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Judge protocol (spec 14.1)
# ---------------------------------------------------------------------------


@dataclass
class JudgeResult:
    """A normalized, validated judge verdict.

    ``score`` 0..1, ``label``/``label_level`` are the ordinal category the
    rubric maps the score into. ``aspects`` holds optional per-aspect scores.
    Non-scoreable calls set ``error`` instead of throwing or fabricating.
    """

    dimension: str
    score: float
    label: str
    label_level: int
    rational: str | None = None
    aspects: dict[str, float] = field(default_factory=dict)
    error: str | None = None


class Judge(Protocol):
    judge_id: str

    def judge(
        self,
        *,
        task_instruction: str,
        rubric: Any,
        output: str,
        dimension: str,
        run_dir: Any = None,
        identity: str | None = None,
    ) -> JudgeResult: ...


# ---------------------------------------------------------------------------
# Judge configuration (spec 14.3 calibration thresholds)
# ---------------------------------------------------------------------------


class JudgementScale(BaseModel):
    """One ordinal category: the lowest ``score`` (min) that receives ``label``."""

    level: int = Field(ge=0)
    label: str
    min: float = Field(ge=0.0, le=1.0)


class JudgeRubric(BaseModel):
    model_config = {"extra": "allow"}

    description: str = ""
    scale: list[JudgementScale] = Field(default_factory=list)

    def categorize(self, score: float) -> tuple[int, str]:
        """Return (label_level, label) for a 0..1 score per the scale (desc min)."""
        if not self.scale:
            level = 1 if score >= 0.5 else 0
            return level, "pass" if level else "fail"
        best: tuple[int, str] | None = None
        for s in sorted(self.scale, key=lambda x: x.min, reverse=True):
            if score >= s.min:
                best = (s.level, s.label)
                break
        if best is None:
            lowest = min(self.scale, key=lambda x: x.min)
            best = (lowest.level, lowest.label)
        return best


class JudgeThresholds(BaseModel):
    """Calibration pass/fail thresholds (spec 14.3)."""

    agreement_min: float = 0.75
    kappa_min: float = 0.60
    order_bias_pp: float = 5.0
    malformed_max: float = 0.01
    pass_threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class JudgeConfig(BaseModel):
    """YAML judge definition under ``configs/judges/``."""

    model_config = {"extra": "forbid"}

    id: str
    dimension: str
    kind: Literal["llm", "offline", "mock"] = "llm"
    model: dict[str, Any] | None = Field(default=None, description="ModelConfig fields")
    rubric: JudgeRubric = Field(default_factory=JudgeRubric)
    prompt_template: str | None = None
    thresholds: JudgeThresholds = Field(default_factory=JudgeThresholds)
    notes: str | None = None


# Default answer-quality prompt per spec 14.2 (task instruction, anchored
# rubric, output, optional deterministic validator results; no model identity).
DEFAULT_JUDGE_PROMPT = """\
You are a rigorous evaluation judge. Score the agent's answer against the rubric.

Task instruction:
{task_instruction}

Rubric:
{rubric}

Agent output:
{output}
{validator_results}
Return a JSON object with EXACTLY these fields:
{{"dimension": str, "score": number (0..1), "label_level": int (ordinal), \
"label": str, "rational": str, "aspects": {{str: number}}}}
"""


def render_rubric(rubric: Any) -> str:
    """Render a rubric (str or JudgeRubric/mapping) for inclusion in a prompt."""
    if isinstance(rubric, str):
        return rubric
    if isinstance(rubric, JudgeRubric):
        lines = [rubric.description] if rubric.description else []
        for s in sorted(rubric.scale, key=lambda x: x.min, reverse=True):
            lines.append(f"- score >= {s.min} -> level {s.level} ({s.label})")
        return "\n".join(lines) or "(no rubric provided)"
    if isinstance(rubric, dict):
        return json.dumps(rubric, sort_keys=True)
    return str(rubric)

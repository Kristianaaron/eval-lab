"""Judge adapters: LLM-backed judge and a deterministic offline mock (spec 14)."""

from __future__ import annotations

from typing import Any

from eval_lab.adapters.base import GenerationRequest, ModelAdapter
from eval_lab.adapters.factory import build_adapter
from eval_lab.judges.protocol import (
    DEFAULT_JUDGE_PROMPT,
    Judge,
    JudgeConfig,
    JudgeEmission,
    JudgeResult,
    parse_judge_json,
    render_rubric,
)
from eval_lab.schemas.models import ModelConfig

# JSON schema handed to the adapter (response_format) and used to validate.
_STRUCTURED_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "dimension": {"type": "string"},
        "score": {"type": "number"},
        "label_level": {"type": "integer"},
        "label": {"type": "string"},
        "rational": {"type": ["string", "null"]},
        "aspects": {"type": "object", "additionalProperties": {"type": "number"}},
    },
    "required": ["dimension", "score", "label_level", "label"],
}


class LLMJudge(Judge):
    """Wrap a ModelAdapter (reuse eval_lab.adapters) as a quality judge.

    The prompt carries the task instruction, anchored rubric, output, and any
    deterministic validator results — never the model's own identity. Malformed
    responses are counted (``malformed_count``) and returned as an error result;
    they are never silently accepted.
    """

    def __init__(self, adapter: ModelAdapter, config: JudgeConfig) -> None:
        self.adapter = adapter
        self.config = config
        self.judge_id = config.id
        self.malformed_count = 0
        self.call_count = 0
        self._prompt_template = config.prompt_template or DEFAULT_JUDGE_PROMPT

    def judge(
        self,
        *,
        task_instruction: str,
        rubric: Any,
        output: str,
        dimension: str,
        run_dir: Any = None,
        identity: str | None = None,
    ) -> JudgeResult:
        self.call_count += 1
        validator_results = _validator_section(run_dir, output)
        prompt = self._prompt_template.format(
            task_instruction=task_instruction or "",
            rubric=render_rubric(rubric),
            output=output,
            validator_results=validator_results,
        )
        req = GenerationRequest(
            prompt=prompt,
            temperature=0.0,
            structured_schema=_STRUCTURED_SCHEMA,
            max_tokens=1024,
        )
        result = self.adapter.generate(req)
        if result.error:
            return JudgeResult(
                dimension=dimension,
                score=0.0,
                label="error",
                label_level=0,
                error=f"adapter error: {result.error}",
            )
        try:
            emission = parse_judge_json(result.text)
        except ValueError as exc:
            self.malformed_count += 1
            return JudgeResult(
                dimension=dimension,
                score=0.0,
                label="malformed",
                label_level=0,
                error=f"malformed judge output: {exc}",
            )
        return _from_emission(emission, dimension)

    def malformed_rate(self) -> float:
        if self.call_count == 0:
            return 0.0
        return self.malformed_count / self.call_count


class OfflineJudge(Judge):
    """Deterministic, clearly-marked mock judge used without any endpoint.

    Scores answer quality from simple text heuristics (deliberately
    length/verbosity-biased) so calibration metrics are meaningful and the full
    pipeline runs offline. It is deterministic and marked ``mock``.
    """

    def __init__(self, config: JudgeConfig) -> None:
        self.config = config
        self.judge_id = config.id
        self.malformed_count = 0
        self.call_count = 0

    def judge(
        self,
        *,
        task_instruction: str,
        rubric: Any,
        output: str,
        dimension: str,
        run_dir: Any = None,
        identity: str | None = None,
    ) -> JudgeResult:
        self.call_count += 1
        score = _mock_quality_score(output)
        level, label = self.config.rubric.categorize(score)
        return JudgeResult(
            dimension=dimension,
            score=round(score, 4),
            label=label,
            label_level=level,
            rational="[mock] deterministic offline heuristic assessment",
            aspects={"length": round(min(1.0, len(output.split()) / 60.0), 4)},
        )

    def malformed_rate(self) -> float:
        if self.call_count == 0:
            return 0.0
        return self.malformed_count / self.call_count


def _mock_quality_score(output: str) -> float:
    s = output.strip()
    if not s:
        return 0.0
    words = len(s.split())
    length_component = min(1.0, words / 60.0)  # verbosity-biased heuristic
    keyword_sources = ("correct", "result", "answer", "done", "solved")
    keyword = 0.25 if any(k in s.lower() for k in keyword_sources) else 0.0
    return min(1.0, length_component * 0.75 + keyword)


def _from_emission(emission: JudgeEmission, dimension: str) -> JudgeResult:
    return JudgeResult(
        dimension=emission.dimension or dimension,
        score=emission.score,
        label=emission.label,
        label_level=emission.label_level,
        rational=emission.rational,
        aspects=emission.aspects,
    )


def _validator_section(run_dir: Any, output: str) -> str:
    """Deterministic validator results appended to the prompt (empty by default)."""
    return ""


def build_judge(config: JudgeConfig, *, offline: bool = False) -> Judge:
    """Build a Judge from its config.

    ``offline=True`` or a ``kind`` of ``mock``/``offline`` returns the
    deterministic mock judge; otherwise a ModelAdapter is built from
    ``config.model`` (reusing the adapter factory; local endpoints supported).
    """
    if offline or config.kind in ("offline", "mock"):
        return OfflineJudge(config)
    if not config.model:
        raise ValueError(
            f"judge {config.id!r}: kind 'llm' requires a 'model' block; "
            "pass --offline or set kind to 'offline' for the mock path"
        )
    adapter = build_adapter(ModelConfig(**config.model))
    return LLMJudge(adapter, config)


__all__ = ["LLMJudge", "OfflineJudge", "build_judge"]

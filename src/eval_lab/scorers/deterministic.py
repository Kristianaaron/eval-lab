"""Deterministic scorers: exact, normalized-exact, regex, json_schema (spec 13.2)."""

from __future__ import annotations

import json
import re
from typing import Any

from eval_lab.schemas.models import ScoreResult
from eval_lab.scorers.base import register_scorer


def _norm(text: str) -> str:
    """Normalize for comparison: lowercase, collapse whitespace, strip punct arts."""
    return re.sub(r"\s+", " ", text.strip().lower())


class ExactScorer:
    scorer_id = "exact"

    def __init__(self, expected: str, normalized: bool = True) -> None:
        self.expected = expected
        self.normalized = normalized

    def score(self, *, output: str, task: Any = None, run_dir: Any = None) -> ScoreResult:
        lhs = _norm(output) if self.normalized else output.strip()
        rhs = _norm(self.expected) if self.normalized else self.expected.strip()
        passed = lhs == rhs
        return ScoreResult(
            scorer_id=self.scorer_id,
            score=1.0 if passed else 0.0,
            passed=passed,
            confidence=1.0,
            required=False,
            details={"expected": self.expected, "output": output},
        )


class RegexScorer:
    scorer_id = "regex"

    def __init__(self, pattern: str, flags: int = re.IGNORECASE) -> None:
        self.pattern = pattern
        self.regex = re.compile(pattern, flags)

    def score(self, *, output: str, task: Any = None, run_dir: Any = None) -> ScoreResult:
        m = self.regex.search(output)
        passed = m is not None
        return ScoreResult(
            scorer_id=self.scorer_id,
            score=1.0 if passed else 0.0,
            passed=passed,
            confidence=1.0,
            required=False,
            details={"pattern": self.pattern, "match": m.group(0) if m else None},
        )


class JsonSchemaScorer:
    """Validate that output parses as JSON matching expected properties.

    Supports: required top-level keys, exact values, and ``type`` checks.
    """

    scorer_id = "json_schema"

    def __init__(
        self,
        expected: dict[str, Any] | None = None,
        properties: dict[str, Any] | None = None,
        required: list[str] | None = None,
        *,
        require_all_keys: bool = True,
    ) -> None:
        """Accept either a JSON-Schema-shaped mapping ({properties, required})
        or flat properties/required arguments (task config form)."""
        if expected is not None:
            if isinstance(expected, dict) and "properties" in expected:
                props = expected.get("properties", {})
                req = expected.get("required", list(props.keys()))
            else:
                props = expected
                req = list(props.keys())
        else:
            props = properties if properties is not None else {}
            req = required if required is not None else list(props.keys())
        self.expected_props = props
        self.required = req
        self.require_all_keys = require_all_keys

    def score(self, *, output: str, task: Any = None, run_dir: Any = None) -> ScoreResult:
        try:
            data = json.loads(output)
        except json.JSONDecodeError as exc:
            return ScoreResult(
                scorer_id=self.scorer_id,
                score=0.0,
                passed=False,
                confidence=1.0,
                required=False,
                error=f"invalid JSON: {exc}",
                details={"expected_required": self.required},
            )

        missing = [k for k in self.required if k not in data]
        type_errors: list[str] = []
        if (
            isinstance(self.expected_props, dict)
            and self.required
            and "type" in self.expected_props
        ):
            # A single-object schema: {<key>: {type: ...}, ...}
            for key, spec in self.expected_props.items():
                if key not in data:
                    continue
                expected_type = spec.get("type") if isinstance(spec, dict) else None
                if expected_type and not _check_type(data[key], expected_type):
                    type_errors.append(f"{key}: expected {expected_type}")
        passed = not missing and not type_errors
        return ScoreResult(
            scorer_id=self.scorer_id,
            score=1.0 if passed else 0.0,
            passed=passed,
            confidence=1.0,
            required=False,
            details={"missing": missing, "type_errors": type_errors},
        )


def _check_type(value: Any, expected: str) -> bool:
    mapping = {
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
    }
    checker = mapping.get(expected)
    return checker(value) if checker else True


class JsonExactScorer:
    """Compare a JSON object answer key-by-key with per-key partial credit.

    Long-context tasks ask several questions at once and expect
    ``{"q1": ..., "q2": ...}``. Each key is compared after normalization
    (case/whitespace-insensitive; numbers compared numerically), the score is
    the fraction of keys that match, and ``passed`` requires every key. A reply
    that is not a JSON object (or a fenced JSON block) scores 0.
    """

    scorer_id = "json_exact"

    def __init__(self, expected: dict[str, Any]) -> None:
        if not isinstance(expected, dict) or not expected:
            raise ValueError("json_exact requires a non-empty 'expected' mapping")
        self.expected = expected

    def score(self, *, output: str, task: Any = None, run_dir: Any = None) -> ScoreResult:
        data = _parse_json_object(output)
        if data is None:
            return ScoreResult(
                scorer_id=self.scorer_id,
                score=0.0,
                passed=False,
                details={"expected": self.expected, "error": "no JSON object found in output"},
            )
        matched: list[str] = []
        mismatched: dict[str, Any] = {}
        for key, want in self.expected.items():
            got = data.get(key)
            if _values_match(got, want):
                matched.append(key)
            else:
                mismatched[key] = {"expected": want, "got": got}
        fraction = len(matched) / len(self.expected)
        return ScoreResult(
            scorer_id=self.scorer_id,
            score=fraction,
            passed=not mismatched,
            details={"matched": matched, "mismatched": mismatched},
        )


_FENCED_JSON = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    candidates = [text.strip()]
    candidates += _FENCED_JSON.findall(text or "")
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for cand in candidates:
        try:
            data = json.loads(cand)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict):
            return data
    return None


def _values_match(got: Any, want: Any) -> bool:
    if isinstance(want, bool) or isinstance(got, bool):
        return bool(got == want)
    if isinstance(want, (int, float)) or isinstance(got, (int, float)):
        try:
            return abs(float(got) - float(want)) < 1e-9
        except (TypeError, ValueError):
            return False
    if isinstance(want, list):
        return (
            isinstance(got, list)
            and len(got) == len(want)
            and all(_values_match(g, w) for g, w in zip(got, want, strict=False))
        )
    if got is None or want is None:
        return bool(got == want)
    return _norm(str(got)).strip(".") == _norm(str(want)).strip(".")


register_scorer("exact", ExactScorer)
register_scorer("json_exact", JsonExactScorer)
register_scorer("regex", RegexScorer)
register_scorer("json_schema", JsonSchemaScorer)

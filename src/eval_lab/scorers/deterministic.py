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


register_scorer("exact", ExactScorer)
register_scorer("regex", RegexScorer)
register_scorer("json_schema", JsonSchemaScorer)

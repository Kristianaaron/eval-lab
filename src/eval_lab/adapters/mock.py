"""Deterministic mock model adapter (spec 11, Phase 0/1).

Fully offline, deterministic reply. Supports fixed-answer mappings so evaluator
tests can exercise exact/regex/json scorers without a network model.
"""

from __future__ import annotations

import json
import zlib

from eval_lab.adapters.base import (
    GenerationRequest,
    GenerationResult,
    HealthStatus,
    ModelAdapter,
    ModelMetadata,
)


class MockModelAdapter(ModelAdapter):
    """Maps a prompt to a stable reply derived only from the request fields.

    Supports an optional ``answer_map`` of exact prompt → text; anything not in
    the map gets a deterministic synthesized reply.
    """

    def __init__(self, answer_map: dict[str, str] | None = None) -> None:
        self._answers = answer_map or {}

    def healthcheck(self) -> HealthStatus:
        return HealthStatus(ok=True, detail="mock")

    def metadata(self) -> ModelMetadata:
        return ModelMetadata(
            provider_type="mock",
            model_name="mock-deterministic-v1",
            supports_tools=True,
            supports_structured_output=True,
            supports_images=False,
        )

    def generate(self, request: GenerationRequest | str) -> GenerationResult:
        if isinstance(request, str):
            request = GenerationRequest(prompt=request)
        # If the prompt has a JSON structure request, synthesize a deterministic
        # JSON object keyed by field name with a stable suffix.
        if request.structured_schema:
            return self._structured(request)
        if request.prompt in self._answers:
            text = self._answers[request.prompt]
        else:
            digest = _stable_token(request.prompt)
            text = f"[mock] deterministic-reply-{digest}"
        return GenerationResult(
            text=text,
            finish_reason="stop",
            prompt_tokens=_token_count(request.prompt),
            completion_tokens=_token_count(text),
        )

    def _structured(self, request: GenerationRequest) -> GenerationResult:
        digest = _stable_token(request.prompt)
        if request.structured_schema:
            # Build a stub object with the same top-level property names.
            props = request.structured_schema.get("properties", {})
            obj = {k: f"mock:{digest}" for k in props}
        else:
            obj = {"result": f"mock:{digest}"}
        text = json.dumps(obj, sort_keys=True)
        return GenerationResult(
            text=text,
            finish_reason="stop",
            prompt_tokens=_token_count(request.prompt),
            completion_tokens=_token_count(text),
        )


def _stable_token(prompt: str) -> str:
    return f"{zlib.crc32(prompt.encode('utf-8')):08x}"


def _token_count(text: str) -> int:
    return max(1, len(text.split()))

"""Deterministic mock model adapter (spec 11, Phase 0).

Provides a fully deterministic, offline ``ModelAdapter`` so the harness can be
developed and tested end to end without a real model or network endpoint.
"""

from __future__ import annotations

import zlib
from typing import Protocol


class HealthStatus:
    ok: bool = True
    detail: str = "mock"


class ModelMetadata:
    provider_type: str = "mock"
    model_name: str = "mock-deterministic-v1"
    supports_tools: bool = True
    supports_structured_output: bool = True


class GenerationRequest:
    """Minimal prompt-in/out request for Phase 0."""

    def __init__(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 128,
    ) -> None:
        self.prompt = prompt
        self.temperature = temperature
        self.max_tokens = max_tokens


class GenerationResult:
    def __init__(
        self,
        text: str,
        *,
        finish_reason: str = "stop",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        self.text = text
        self.finish_reason = finish_reason
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class ModelAdapter(Protocol):
    def healthcheck(self) -> HealthStatus: ...
    def metadata(self) -> ModelMetadata: ...
    def generate(self, request: GenerationRequest) -> GenerationResult: ...


class MockModelAdapter:
    """Deterministically maps a prompt to a stable reply.

    The reply is derived only from the request fields, so identical inputs
    always produce identical outputs. Used by ``eval-lab doctor`` and by the
    Phase 0 test suite.
    """

    def healthcheck(self) -> HealthStatus:
        return HealthStatus()

    def metadata(self) -> ModelMetadata:
        return ModelMetadata()

    def generate(self, request: GenerationRequest | str) -> GenerationResult:
        prompt = request if isinstance(request, str) else request.prompt
        # Deterministic reply: echo a fixed marker plus a stable hash token so
        # repeat calls are byte-identical but visibly prompt-correlated.
        digest = _stable_token(prompt)
        text = f"[mock] deterministic-reply-{digest}"
        return GenerationResult(
            text=text,
            finish_reason="stop",
            prompt_tokens=_token_count(prompt),
            completion_tokens=_token_count(text),
        )


def _stable_token(prompt: str) -> str:
    # zlib crc32 is deterministic across interpreter runs for the same bytes.
    return f"{zlib.crc32(prompt.encode('utf-8')):08x}"


def _token_count(text: str) -> int:
    # Simple whitespace token estimator for the mock; never treated as real.
    return max(1, len(text.split()))

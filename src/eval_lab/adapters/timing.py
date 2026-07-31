"""Synthetic streaming adapter for the hardware/performance suite (spec 15).

Emits a deterministic reply while streaming tokens at a configurable first-token
delay and decode rate, recording per-token monotonic wall-clock timestamps. This
gives the perf runner raw timestamps from which time-to-first-token and decode
throughput are recomputed and verified without a real model server.
"""

from __future__ import annotations

import time

from eval_lab.adapters.base import (
    GenerationRequest,
    GenerationResult,
    GenerationTiming,
    HealthStatus,
    ModelAdapter,
    ModelMetadata,
    TokenCallback,
)

DEFAULT_REPLY = "[mock] deterministic-reply-timed"


class TimedMockAdapter(ModelAdapter):
    """Deterministic, streamable mock with simulated TTFT and decode latency."""

    def __init__(
        self,
        *,
        text: str | None = None,
        first_token_delay_s: float = 0.05,
        tokens_per_s: float = 20.0,
    ) -> None:
        self.text = text or DEFAULT_REPLY
        self.first_token_delay_s = first_token_delay_s
        self.tokens_per_s = tokens_per_s

    def healthcheck(self) -> HealthStatus:
        return HealthStatus(ok=True, detail="timed-mock")

    def metadata(self) -> ModelMetadata:
        return ModelMetadata(
            provider_type="mock-timed",
            model_name="mock-timed-v1",
            supports_tools=False,
            supports_structured_output=False,
            supports_images=False,
        )

    def generate(self, request: GenerationRequest) -> GenerationResult:
        start = time.monotonic()
        time.sleep(self.first_token_delay_s)
        tokens = self.text.split()
        decode = (len(tokens) - 1) / self.tokens_per_s if len(tokens) > 1 else 0.0
        time.sleep(decode)
        total = time.monotonic() - start
        return GenerationResult(
            text=self.text,
            finish_reason="stop",
            prompt_tokens=max(1, len(request.prompt.split())),
            completion_tokens=len(tokens),
            timing=self._timing(tokens, total),
        )

    def generate_stream(
        self, request: GenerationRequest, on_token: TokenCallback
    ) -> GenerationResult:
        request_start = time.monotonic()
        time.sleep(self.first_token_delay_s)
        tokens = self.text.split()
        decode = (len(tokens) - 1) / self.tokens_per_s if len(tokens) > 1 else 0.0
        step = decode / (len(tokens) - 1) if len(tokens) > 1 else 0.0
        for i, tok in enumerate(tokens):
            on_token(tok, time.monotonic())
            if i < len(tokens) - 1:
                time.sleep(step)
        total = time.monotonic() - request_start
        return GenerationResult(
            text=self.text,
            finish_reason="stop",
            prompt_tokens=max(1, len(request.prompt.split())),
            completion_tokens=len(tokens),
            timing=self._timing(tokens, total),
        )

    def _timing(self, tokens: list[str], total: float) -> GenerationTiming:
        decode = (len(tokens) - 1) / self.tokens_per_s if len(tokens) > 1 else 0.0
        return GenerationTiming(
            ttft_s=self.first_token_delay_s,
            decode_duration_s=decode,
            decode_tokens_per_s=self.tokens_per_s if len(tokens) > 1 else None,
            total_latency_s=total,
        )

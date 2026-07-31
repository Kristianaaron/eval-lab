"""Shared model-adapter protocol and normalized result types (spec 11)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class HealthStatus:
    ok: bool = True
    detail: str = "ok"


@dataclass
class ModelMetadata:
    provider_type: str = "unknown"
    model_name: str = "unknown"
    supports_tools: bool = False
    supports_structured_output: bool = False
    supports_images: bool = False


@dataclass
class GenerationRequest:
    prompt: str
    system_prompt: str | None = None
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 4096
    stop: list[str] = field(default_factory=list)
    seed: int | None = None
    structured_schema: dict[str, Any] | None = None
    messages: list[dict[str, Any]] | None = None


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class GenerationTiming:
    """Wall-clock performance for one generation (spec 15.1).

    — ``ttft_s``: request arrival → first token.
    — ``decode_duration_s``: first token → last token.
    — ``decode_tokens_per_s``: generated tokens / decode_duration_s.
    — ``total_latency_s``: request → completion (recorded at the adapter boundary).
    """

    ttft_s: float | None = None
    decode_duration_s: float | None = None
    decode_tokens_per_s: float | None = None
    prefill_tokens_per_s: float | None = None
    total_latency_s: float | None = None


@dataclass
class GenerationResult:
    text: str
    finish_reason: str = "stop"  # stop | length | tool_calls | error | ...
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    logprobs: Any | None = None
    error: str | None = None
    timing: GenerationTiming | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ModelAdapter(Protocol):
    def healthcheck(self) -> HealthStatus: ...
    def metadata(self) -> ModelMetadata: ...
    def generate(self, request: GenerationRequest) -> GenerationResult: ...


TokenCallback = Callable[[str, float], None]  # (token text, monotonic wall seconds)


@runtime_checkable
class StreamingModelAdapter(Protocol):
    """An adapter that can stream tokens with per-token wall-clock timestamps.

    ``on_token(text, wall_time_s)`` is invoked for every generated token; the
    wall clock is ``time.monotonic()`` seconds. This lets the harness record
    raw token timestamps from which time-to-first-token and decode throughput
    are recomputed and verified (spec 15.1 exit gate).
    """

    def generate_stream(
        self, request: GenerationRequest, on_token: TokenCallback
    ) -> GenerationResult: ...

"""Shared model-adapter protocol and normalized result types (spec 11)."""

from __future__ import annotations

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
class GenerationResult:
    text: str
    finish_reason: str = "stop"  # stop | length | tool_calls | error | ...
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    logprobs: Any | None = None
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ModelAdapter(Protocol):
    def healthcheck(self) -> HealthStatus: ...
    def metadata(self) -> ModelMetadata: ...
    def generate(self, request: GenerationRequest) -> GenerationResult: ...

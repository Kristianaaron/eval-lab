"""Model adapter factory (spec 11)."""

from __future__ import annotations

from eval_lab.adapters.base import ModelAdapter
from eval_lab.adapters.mock import MockModelAdapter
from eval_lab.adapters.openai_compatible import OpenAICompatibleAdapter
from eval_lab.schemas.models import ModelConfig


def build_adapter(config: ModelConfig, *, answer_map: dict[str, str] | None = None) -> ModelAdapter:
    """Build a ModelAdapter from a ModelConfig (Phase 1: mock + openai_compatible)."""
    if config.provider_type == "mock":
        return MockModelAdapter(answer_map=answer_map)
    if config.provider_type in ("openai_compatible", "vllm", "sglang", "llama_cpp"):
        if not config.endpoint:
            raise ValueError(f"provider {config.provider_type} requires an endpoint")
        key = _resolve_api_key(config)
        return OpenAICompatibleAdapter(
            base_url=config.endpoint,
            model_name=config.model_name,
            api_key=key,
        )
    raise ValueError(f"unsupported provider_type: {config.provider_type}")


def _resolve_api_key(config: ModelConfig) -> str | None:
    # Support "!cat <path>" syntax for loading keys from local files.
    endpoint_key = getattr(config, "api_key", None)
    if isinstance(endpoint_key, str):
        if endpoint_key.startswith("!cat "):
            try:
                from pathlib import Path

                return Path(endpoint_key[5:].strip()).read_text().strip()
            except OSError:
                return None
        return endpoint_key
    return None

"""OpenAI-compatible HTTP model adapter (spec 11; Phase 1 + 7).

Talks to any OpenAI-compatible /chat/completions endpoint (vLLM, SGLang,
llama.cpp server, localhost gateways). Uses only stdlib+urllib to avoid a hard
dependency on the ``openai`` SDK; the SDK variant can be added later.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from eval_lab.adapters.base import (
    GenerationRequest,
    GenerationResult,
    HealthStatus,
    ModelAdapter,
    ModelMetadata,
    ToolCall,
)


class OpenAICompatibleAdapter(ModelAdapter):
    def __init__(
        self,
        base_url: str,
        model_name: str,
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.api_key = api_key
        self.timeout = timeout

    def _url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def healthcheck(self) -> HealthStatus:
        try:
            # A trivial 1-token request verifies the endpoint is alive.
            result = self.generate(GenerationRequest(prompt="ping", max_tokens=1))
            return HealthStatus(ok=result.error is None, detail=result.error or "ok")
        except Exception as exc:  # pragma: no cover - network dependent
            return HealthStatus(ok=False, detail=str(exc))

    def metadata(self) -> ModelMetadata:
        return ModelMetadata(
            provider_type="openai_compatible",
            model_name=self.model_name,
            supports_tools=True,
            supports_structured_output=True,
            supports_images=False,
        )

    def generate(self, request: GenerationRequest) -> GenerationResult:
        messages: list[dict[str, Any]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        if request.messages:
            messages.extend(request.messages)
        else:
            messages.append({"role": "user", "content": request.prompt})

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.stop:
            payload["stop"] = request.stop
        if request.seed is not None:
            payload["seed"] = request.seed
        if request.structured_schema:
            payload["response_format"] = {"type": "json_object"}
            payload["response_format"]["json_schema"] = request.structured_schema
        # Always request tool-call capability; empty tools means plain chat.
        payload.setdefault("tools", None)

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self._url(), data=body, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            return GenerationResult(text="", finish_reason="error", error=str(exc), raw={})

        return _parse_choice(data)


def _parse_choice(data: dict[str, Any]) -> GenerationResult:
    usage = data.get("usage") or {}
    result = GenerationResult(
        text="",
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        raw=data,
    )
    choices = data.get("choices") or []
    if not choices:
        result.finish_reason = "error"
        result.error = "no choices returned"
        return result
    choice = choices[0]
    message = choice.get("message") or {}
    result.text = message.get("content") or ""
    result.finish_reason = choice.get("finish_reason") or "stop"
    for tc in message.get("tool_calls") or []:
        fn = (tc.get("function") or {}).get("name")
        result.tool_calls.append(
            ToolCall(
                id=tc.get("id") or "",
                name=str(fn),
                arguments=_safe_json((tc.get("function") or {}).get("arguments")),
            )
        )
    return result


def _safe_json(s: Any) -> dict[str, Any]:
    if isinstance(s, dict):
        return s
    if isinstance(s, str):
        try:
            parsed = json.loads(s)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}

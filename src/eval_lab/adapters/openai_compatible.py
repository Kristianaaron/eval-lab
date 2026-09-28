"""OpenAI-compatible HTTP model adapter (spec 11; Phase 1 + 7).

Talks to any OpenAI-compatible server (vLLM, SGLang, llama.cpp server, LM
Studio, Ollama, localhost gateways). Uses only stdlib ``urllib`` to avoid a hard
dependency on the ``openai`` SDK.

Two request paths:

- ``/chat/completions`` for generation, including native tool calling when the
  request carries tool definitions.
- ``/completions`` with ``echo`` + ``logprobs`` for scoring a supplied text
  (perplexity). vLLM and SGLang support this; servers that do not return
  prompt log-probabilities produce an explicit error, never a fake number.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from eval_lab.adapters.base import (
    GenerationRequest,
    GenerationResult,
    HealthStatus,
    LogprobResult,
    ModelAdapter,
    ModelMetadata,
    TokenLogprob,
    ToolCall,
)


class OpenAICompatibleAdapter(ModelAdapter):
    def __init__(
        self,
        base_url: str,
        model_name: str,
        api_key: str | None = None,
        timeout: float = 600.0,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.api_key = api_key
        self.timeout = timeout
        # Server-specific knobs merged into every request body (e.g. vLLM
        # ``chat_template_kwargs``); recorded so a run stays reproducible.
        self.extra_body = dict(extra_body or {})

    def _url(self, path: str = "/chat/completions") -> str:
        return f"{self.base_url}{path}"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url(path), data=body, headers=self._headers(), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"HTTP {exc.code} from {path}: {detail}") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"unexpected response shape from {path}")
        return data

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

    # -- generation ---------------------------------------------------------
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
            "top_p": request.top_p,
            "max_tokens": request.max_tokens,
        }
        if request.stop:
            payload["stop"] = request.stop
        if request.seed is not None:
            payload["seed"] = request.seed
        if request.structured_schema:
            payload["response_format"] = {"type": "json_object"}
        if request.tools:
            payload["tools"] = request.tools
            payload["tool_choice"] = "auto"
        payload.update(self.extra_body)

        try:
            data = self._post("/chat/completions", payload)
        except Exception as exc:
            return GenerationResult(text="", finish_reason="error", error=str(exc), raw={})
        return _parse_choice(data)

    # -- scoring (perplexity) -----------------------------------------------
    def prompt_logprobs(self, text: str) -> LogprobResult:
        """Log-probability of every token of ``text`` via ``/completions`` echo.

        ``max_tokens=1`` (not 0) because several servers reject a zero budget;
        the single generated token is dropped using ``usage.prompt_tokens``.
        """
        payload: dict[str, Any] = {
            "model": self.model_name,
            "prompt": text,
            "max_tokens": 1,
            "temperature": 0.0,
            "echo": True,
            "logprobs": 1,
        }
        payload.update(self.extra_body)
        try:
            data = self._post("/completions", payload)
        except Exception as exc:
            return LogprobResult(error=f"logprob request failed: {exc}")
        return _parse_logprobs(data, text)


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
    if result.tool_calls and result.finish_reason == "stop":
        result.finish_reason = "tool_calls"
    return result


def _parse_logprobs(data: dict[str, Any], text: str) -> LogprobResult:
    choices = data.get("choices") or []
    if not choices:
        return LogprobResult(error="no choices returned", raw=data)
    choice = choices[0]
    lp = choice.get("logprobs")
    if not isinstance(lp, dict):
        return LogprobResult(
            error="server returned no logprobs (echo/logprobs unsupported on /completions)",
            raw=data,
        )
    tokens = lp.get("tokens")
    values = lp.get("token_logprobs")
    if not isinstance(tokens, list) or not isinstance(values, list):
        # vLLM ``prompt_logprobs`` shape: list[dict[token_id -> {logprob, decoded_token}]]
        prompt_lp = choice.get("prompt_logprobs")
        if isinstance(prompt_lp, list):
            out: list[TokenLogprob] = []
            for entry in prompt_lp:
                if not entry:
                    out.append(TokenLogprob(token="", logprob=None))
                    continue
                best = max(entry.values(), key=lambda v: v.get("rank", 1) * -1)
                out.append(
                    TokenLogprob(
                        token=str(best.get("decoded_token", "")), logprob=float(best["logprob"])
                    )
                )
            return LogprobResult(tokens=out, raw=data)
        return LogprobResult(error="logprobs payload missing tokens/token_logprobs", raw=data)

    usage = data.get("usage") or {}
    n_prompt = usage.get("prompt_tokens")
    n = int(n_prompt) if isinstance(n_prompt, int) and 0 < n_prompt <= len(tokens) else len(tokens)
    # Echo returns the prompt followed by the generated token(s); keep the prompt only.
    if n == len(tokens) and choice.get("text", "") != text and len(tokens) > 1:
        n = len(tokens) - 1
    out = []
    for tok, val in zip(tokens[:n], values[:n], strict=False):
        out.append(TokenLogprob(token=str(tok), logprob=float(val) if val is not None else None))
    return LogprobResult(tokens=out, raw=data)


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

"""Local Hugging Face adapter (optional): generation + exact token log-probs.

Only imported when ``provider_type == "hf_local"``. Requires the ``hf`` extra
(``torch`` + ``transformers``); the import error is surfaced verbatim so a
missing dependency is never mistaken for a model problem.

Perplexity through this adapter is a true teacher-forced forward pass over the
checkpoint, which makes it the reference measurement to compare a served
(quantized / pruned) endpoint against.
"""

from __future__ import annotations

from typing import Any

from eval_lab.adapters.base import (
    GenerationRequest,
    GenerationResult,
    HealthStatus,
    LogprobResult,
    ModelAdapter,
    ModelMetadata,
    TokenLogprob,
)


class HFLocalAdapter(ModelAdapter):
    def __init__(
        self,
        model_path: str,
        *,
        device: str | None = None,
        dtype: str | None = None,
        trust_remote_code: bool = False,
        max_length: int = 8192,
    ) -> None:
        try:
            import torch  # type: ignore[import-not-found]
            from transformers import (  # type: ignore[import-not-found]
                AutoModelForCausalLM,
                AutoTokenizer,
            )
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "hf_local provider requires the 'hf' extra: uv pip install -e '.[hf]'"
            ) from exc
        self._torch = torch
        self.model_path = model_path
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        torch_dtype = getattr(torch, dtype) if dtype else None
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path, trust_remote_code=trust_remote_code
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path, torch_dtype=torch_dtype, trust_remote_code=trust_remote_code
        ).to(self.device)
        self.model.eval()
        self.max_length = max_length

    def healthcheck(self) -> HealthStatus:
        return HealthStatus(ok=True, detail=f"hf_local:{self.device}")

    def metadata(self) -> ModelMetadata:
        return ModelMetadata(
            provider_type="hf_local",
            model_name=self.model_path,
            supports_tools=False,
            supports_structured_output=False,
        )

    def generate(self, request: GenerationRequest) -> GenerationResult:  # pragma: no cover
        torch = self._torch
        messages: list[dict[str, Any]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend(request.messages or [{"role": "user", "content": request.prompt}])
        if getattr(self.tokenizer, "chat_template", None):
            ids = self.tokenizer.apply_chat_template(
                messages, add_generation_prompt=True, return_tensors="pt"
            )
        else:
            ids = self.tokenizer(request.prompt, return_tensors="pt").input_ids
        ids = ids.to(self.device)
        with torch.no_grad():
            out = self.model.generate(
                ids,
                max_new_tokens=request.max_tokens,
                do_sample=request.temperature > 0,
                temperature=max(request.temperature, 1e-5),
                top_p=request.top_p,
            )
        new_tokens = out[0, ids.shape[1] :]
        text = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
        return GenerationResult(
            text=text,
            finish_reason="length" if len(new_tokens) >= request.max_tokens else "stop",
            prompt_tokens=int(ids.shape[1]),
            completion_tokens=int(len(new_tokens)),
        )

    def prompt_logprobs(self, text: str) -> LogprobResult:  # pragma: no cover
        torch = self._torch
        enc = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=self.max_length)
        ids = enc.input_ids.to(self.device)
        with torch.no_grad():
            logits = self.model(ids).logits
        logprobs = torch.log_softmax(logits[0, :-1].float(), dim=-1)
        target = ids[0, 1:]
        picked = logprobs.gather(1, target.unsqueeze(1)).squeeze(1).tolist()
        pieces = self.tokenizer.convert_ids_to_tokens(ids[0].tolist())
        tokens = [
            TokenLogprob(token=self.tokenizer.convert_tokens_to_string([pieces[0]]), logprob=None)
        ]
        for piece, lp in zip(pieces[1:], picked, strict=False):
            tokens.append(
                TokenLogprob(token=self.tokenizer.convert_tokens_to_string([piece]), logprob=lp)
            )
        return LogprobResult(tokens=tokens)

"""Perplexity runner (spec 13.4): score a fixed corpus under the model.

Perplexity is an *intrinsic* language-modelling metric: how surprised the model
is by held-out text. It is the most sensitive early signal of damage from
quantization, pruning or runtime kernel changes, which is why every model
report should carry it next to task pass rates.

Method
------
The corpus (every attachment of the task, concatenated) is cut into windows of
``window_chars`` characters (default ~6 000 chars ≈ 1.5k tokens). Each window is
scored independently with the adapter's ``prompt_logprobs`` (server-side echo
logprobs, or a local Hugging Face forward pass); the first token of each
window has no context and is excluded. Reported metrics:

- ``perplexity``       = exp(mean negative log-likelihood per scored token)
- ``bits_per_token``   = mean NLL / ln 2
- ``bits_per_byte``    = total NLL / (ln 2 · UTF-8 bytes of scored text) — the
  tokenizer-independent number to compare *different* models on.
- ``tokens``, ``bytes``, ``windows``, ``elapsed_s``

Windowing without overlap slightly overstates perplexity versus a sliding
evaluation; it is deterministic and identical for every model, which is what a
regression benchmark needs. ``stride_chars`` < ``window_chars`` enables overlap
where only the trailing ``window_chars - stride_chars`` characters of each
window are scored (classic strided evaluation).

An adapter that cannot return log-probabilities yields a run with
``status=error`` and an explicit message. A perplexity of 0 is never emitted.
"""

from __future__ import annotations

import json
import math
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from eval_lab.adapters.base import LogprobModelAdapter, LogprobResult
from eval_lab.reports.markdown import write_run_report
from eval_lab.runners.direct import RunContext, RunResult
from eval_lab.schemas.models import RunManifest, TaskSpec
from eval_lab.scorers.aggregate import score_oracle
from eval_lab.storage.artifacts import RunWorkspace
from eval_lab.tasks.resolve import read_attachments, read_instruction
from eval_lab.traces.recorder import TraceRecorder

DEFAULT_WINDOW_CHARS = 6_000
DEFAULT_MAX_CHARS = 400_000


def corpus_text(task: TaskSpec) -> str:
    """Concatenate every attachment; fall back to the instruction file itself."""
    parts = [text for _, text in read_attachments(task)]
    if not parts:
        parts = [read_instruction(task)]
    return "\n\n".join(parts)


def windows(text: str, window_chars: int, stride_chars: int | None = None) -> list[tuple[int, str]]:
    """Split ``text`` into ``(scored_from, window_text)`` pieces.

    ``scored_from`` is the character offset inside the window from which tokens
    count toward the metric (0 for non-overlapping windows).
    """
    if window_chars <= 0:
        raise ValueError("window_chars must be positive")
    stride = stride_chars or window_chars
    if stride <= 0 or stride > window_chars:
        raise ValueError("stride_chars must be in (0, window_chars]")
    out: list[tuple[int, str]] = []
    start = 0
    while start < len(text):
        end = min(start + window_chars, len(text))
        scored_from = 0 if start == 0 else window_chars - stride
        out.append((scored_from, text[start:end]))
        if end == len(text):
            break
        start += stride
    return out


def _scored_logprobs(result: LogprobResult, scored_from: int) -> tuple[list[float], int]:
    """Log-probs for tokens at/after ``scored_from`` chars, plus scored byte count."""
    if scored_from <= 0:
        all_bytes = sum(
            len(t.token.encode("utf-8")) for t in result.tokens if t.logprob is not None
        )
        return result.scored, all_bytes
    pos = 0
    lps: list[float] = []
    nbytes = 0
    for tok in result.tokens:
        pos += len(tok.token)
        if pos > scored_from and tok.logprob is not None:
            lps.append(tok.logprob)
            nbytes += len(tok.token.encode("utf-8"))
    return lps, nbytes


def compute_metrics(
    adapter: LogprobModelAdapter,
    text: str,
    *,
    window_chars: int = DEFAULT_WINDOW_CHARS,
    stride_chars: int | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    on_window: Any = None,
) -> dict[str, Any]:
    """Score ``text`` and return the metrics dict (raises on backend error)."""
    text = text[:max_chars]
    total_nll = 0.0
    n_tokens = 0
    n_bytes = 0
    per_window: list[dict[str, Any]] = []
    started = time.monotonic()
    pieces = windows(text, window_chars, stride_chars)
    for idx, (scored_from, piece) in enumerate(pieces):
        res = adapter.prompt_logprobs(piece)
        if res.error:
            raise RuntimeError(res.error)
        lps, nbytes = _scored_logprobs(res, scored_from)
        if not lps:
            continue
        nll = -sum(lps)
        total_nll += nll
        n_tokens += len(lps)
        n_bytes += nbytes
        per_window.append(
            {"window": idx, "tokens": len(lps), "nll": nll, "perplexity": math.exp(nll / len(lps))}
        )
        if on_window:
            on_window(idx + 1, len(pieces))
    if n_tokens == 0:
        raise RuntimeError("no tokens were scored (empty corpus or backend returned no logprobs)")
    mean_nll = total_nll / n_tokens
    return {
        "perplexity": math.exp(mean_nll),
        "mean_nll": mean_nll,
        "bits_per_token": mean_nll / math.log(2),
        "bits_per_byte": total_nll / (math.log(2) * max(n_bytes, 1)),
        "tokens": n_tokens,
        "bytes": n_bytes,
        "chars": len(text),
        "windows": len(per_window),
        "window_chars": window_chars,
        "stride_chars": stride_chars or window_chars,
        "elapsed_s": time.monotonic() - started,
        "per_window": per_window,
    }


class PerplexityRunner:
    """Executes tasks whose ``execution.runner == 'perplexity'``."""

    def execute_task(self, task: TaskSpec, context: RunContext) -> RunResult:
        run_id = uuid.uuid4().hex[:12]
        ws = RunWorkspace(context.runs_root, run_id)
        recorder = TraceRecorder(run_id, ws.trace_path())
        recorder.record("run_start", {"task_id": task.id, "model_id": context.model_id})

        params = dict(task.execution.parameters)
        params.update(context.extra.get("perplexity") or {})
        window_chars = int(params.get("window_chars", DEFAULT_WINDOW_CHARS))
        stride_raw = params.get("stride_chars")
        stride_chars = int(stride_raw) if stride_raw else None
        max_chars = int(params.get("max_chars", DEFAULT_MAX_CHARS))

        text = context.extra.get("corpus_text")
        if text is None:
            text = corpus_text(task)

        error: str | None = None
        metrics: dict[str, Any] = {}
        start = time.monotonic()
        adapter = context.model
        if not isinstance(adapter, LogprobModelAdapter):
            error = (
                f"model adapter {type(adapter).__name__} cannot return token log-probabilities; "
                "use an OpenAI-compatible server with /completions echo+logprobs "
                "(vLLM, SGLang) or the hf_local provider"
            )
        else:
            try:
                metrics = compute_metrics(
                    adapter,
                    text,
                    window_chars=window_chars,
                    stride_chars=stride_chars,
                    max_chars=max_chars,
                    on_window=lambda i, n: recorder.record(
                        "perplexity_window", {"done": i, "total": n}
                    ),
                )
            except Exception as exc:
                error = str(exc)
                recorder.record("exception", {"error": error})
        duration = time.monotonic() - start
        recorder.record("run_completion", {"duration_s": duration, "error": error})

        aggregate = None
        scores: list[Any] = []
        output = ""
        if not error:
            summary = {k: v for k, v in metrics.items() if k != "per_window"}
            output = json.dumps(summary, sort_keys=True)
            (ws.root / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
            aggregate = score_oracle(task, output=output, run_dir=ws.root)
            scores = aggregate.scores
            ws.append_scores([s.model_dump() for s in scores])

        manifest = RunManifest(
            run_id=run_id,
            created_at=datetime.now(UTC),
            task_id=task.id,
            task_version=task.version,
            model_id=context.model_id,
            harness_id=context.harness_id or "perplexity",
            random_seed=context.seed,
            budgets={"window_chars": window_chars, "max_chars": max_chars},
            warm_state=context.extra.get("warm_state", "model"),
            result_status="completed" if not error else "error",
        ).model_dump(mode="json") | {
            "run_dir": str(ws.root),
            "level": task.level.value,
            "aggregate_score": aggregate.total if aggregate else None,
            "passed": bool(aggregate.passed) if aggregate else False,
            "duration_s": duration,
            "metrics": {k: v for k, v in metrics.items() if k != "per_window"},
        }
        ws.write_manifest(manifest)
        ws.write_result(
            {
                "run_id": run_id,
                "output": output,
                "error": error,
                "metrics": {k: v for k, v in metrics.items() if k != "per_window"},
                "aggregate": aggregate.total if aggregate else None,
                "passed": bool(aggregate.passed) if aggregate else False,
                "scores": [s.model_dump() for s in scores],
                "duration_s": duration,
            }
        )
        recorder.close()
        write_run_report(ws.root)

        status = "completed" if not error else "error"
        if context.store:
            context.store.insert_run(manifest)
            if scores:
                context.store.insert_scores(run_id, [s.model_dump() for s in scores])
            context.store.update_status(
                run_id,
                status,
                aggregate=aggregate.total if aggregate else None,
                passed=bool(aggregate.passed) if aggregate else False,
            )
        return RunResult(
            run_id=run_id,
            run_dir=str(ws.root),
            output=output,
            aggregate=aggregate,
            scores=scores,
            manifest=manifest,
            status=status,
            duration_s=duration,
            error=error,
        )

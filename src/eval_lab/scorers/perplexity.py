"""Perplexity scorer (spec 13.4): mean negative log-likelihood.

Computes perplexity from the token-level logprobs returned by the model
adapter.  Lower = more confident.  Exposed as ``perplexity`` scorer_id.
"""

from __future__ import annotations

import math
from typing import Any

from eval_lab.schemas.models import ScoreResult
from eval_lab.scorers.base import register_scorer


class PerplexityScorer:
    scorer_id = "perplexity"

    def __init__(self, *, target_ppl: float | None = None) -> None:
        self.target_ppl = target_ppl

    def score(
        self,
        *,
        output: str,
        task: Any = None,
        run_dir: Any = None,
        logprobs: Any = None,
        **kwargs: Any,
    ) -> ScoreResult:
        if not logprobs:
            return ScoreResult(
                scorer_id=self.scorer_id,
                score=0.0,
                passed=False,
                confidence=0.0,
                required=False,
                error="no logprobs available",
                details={"output": output},
            )
        logp = [float(e.get("logprob", 0.0)) for e in logprobs if isinstance(e, dict)]
        if not logp:
            return ScoreResult(
                scorer_id=self.scorer_id,
                score=0.0,
                passed=False,
                confidence=0.0,
                required=False,
                error="empty logprobs list",
                details={"output": output},
            )
        n = len(logp)
        mean_nll = -sum(logp) / n
        ppl = math.exp(mean_nll)
        score = max(0.0, min(1.0, 1.0 / (1.0 + ppl / 100.0)))
        passed = True
        if self.target_ppl is not None:
            passed = ppl <= float(self.target_ppl)
        return ScoreResult(
            scorer_id=self.scorer_id,
            score=score,
            passed=passed,
            confidence=1.0,
            required=False,
            details={
                "perplexity": round(ppl, 4),
                "mean_nll": round(mean_nll, 4),
                "tokens": n,
                "target_ppl": self.target_ppl,
            },
        )


register_scorer(PerplexityScorer.scorer_id, PerplexityScorer)
"""perplexity scorer: threshold + normalized score over run metrics (spec 13.4)."""

from __future__ import annotations

import json
import math
from typing import Any

from eval_lab.schemas.models import ScoreResult
from eval_lab.scorers.base import register_scorer


class PerplexityScorer:
    """Turn a perplexity measurement into a pass/fail plus a 0-1 score.

    The perplexity runner hands the scorer a JSON metrics summary as ``output``.

    Config:
        max_perplexity   pass iff perplexity <= this (default: no gate, always pass).
        reference        perplexity that maps to score 0 (default 1000). Score is
                         ``1 - ln(ppl) / ln(reference)`` clamped to [0, 1], so a
                         perplexity of 1 scores 1.0, 10 → ~0.67, 100 → ~0.33.
        metric           which metric to gate on: perplexity | bits_per_byte.
    """

    scorer_id = "perplexity"

    def __init__(
        self,
        max_perplexity: float | None = None,
        reference: float = 1000.0,
        metric: str = "perplexity",
    ) -> None:
        if reference <= 1.0:
            raise ValueError("reference perplexity must be > 1")
        if metric not in ("perplexity", "bits_per_byte"):
            raise ValueError("metric must be 'perplexity' or 'bits_per_byte'")
        self.max_perplexity = max_perplexity
        self.reference = reference
        self.metric = metric

    def score(self, *, output: str, task: Any = None, run_dir: Any = None) -> ScoreResult:
        try:
            metrics = json.loads(output)
        except (TypeError, json.JSONDecodeError):
            return ScoreResult(
                scorer_id=self.scorer_id,
                error="perplexity scorer expects a JSON metrics summary as output",
            )
        ppl = metrics.get("perplexity")
        if not isinstance(ppl, (int, float)) or ppl <= 0 or math.isnan(ppl):
            return ScoreResult(scorer_id=self.scorer_id, error="metrics lack a valid perplexity")
        value = ppl if self.metric == "perplexity" else float(metrics.get("bits_per_byte", 0.0))
        normalized = 1.0 - math.log(max(ppl, 1.0)) / math.log(self.reference)
        normalized = min(1.0, max(0.0, normalized))
        passed = True if self.max_perplexity is None else value <= self.max_perplexity
        return ScoreResult(
            scorer_id=self.scorer_id,
            score=normalized,
            passed=passed,
            details={
                "perplexity": ppl,
                "bits_per_byte": metrics.get("bits_per_byte"),
                "bits_per_token": metrics.get("bits_per_token"),
                "tokens": metrics.get("tokens"),
                "gate_metric": self.metric,
                "max_perplexity": self.max_perplexity,
                "reference": self.reference,
            },
        )


register_scorer("perplexity", PerplexityScorer)

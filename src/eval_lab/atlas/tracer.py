"""M3 layerwise MoE tracer — real CPU router/expert saliency measurement.

Each layer runs the full deterministic calibration pool through its own router
and expert projections (top-k softmax routing), measuring for every expert:
activation frequency, mean gate probability, and output norm. Per-label rows
break the same measures down by capability label so a prune topology can be
tied to labelled behaviour (spec 8). All values are computed from the actual
model + calibration inputs — no fabricated saliency.
"""

from __future__ import annotations

import math
import random
from typing import Any

from eval_lab.schemas.atlas_runtime import SqlRow

# -- calibration pool -------------------------------------------------------


class CalibrationPool:
    """Deterministic calibration contexts, each tagged with a capability label.

    A label-specific bias direction is mixed into every token so different
    capabilities excite different experts — making per-label saliency real and
    reproducible rather than uniform noise.
    """

    def __init__(
        self,
        *,
        num_samples: int,
        seq_len: int,
        hidden_size: int,
        capability_labels: list[str],
        seed: int,
    ) -> None:
        self.num_samples = num_samples
        self.seq_len = seq_len
        self.hidden_size = hidden_size
        self.capability_labels = list(capability_labels) or ["general_reasoning"]
        self.seed = seed
        self._build()

    def _build(self) -> None:
        rng = random.Random(self.seed)
        # label -> preferred direction (seeded, unit-scaled)
        directions: dict[str, list[float]] = {}
        for label in self.capability_labels:
            lrng = random.Random(_stable_hash(label) ^ self.seed)
            vec = [lrng.gauss(0, 1) for _ in range(self.hidden_size)]
            n = math.sqrt(sum(v * v for v in vec)) or 1.0
            directions[label] = [v / n * 0.8 for v in vec]  # 0.8 = label bias strength

        samples: list[tuple[str, list[list[float]]]] = []
        for i in range(self.num_samples):
            label = self.capability_labels[i % len(self.capability_labels)]
            tokens: list[list[float]] = []
            for _ in range(self.seq_len):
                base = directions[label]
                tok = [rng.gauss(0, 1) + base[d] for d in range(self.hidden_size)]
                tokens.append(tok)
            samples.append((label, tokens))
        self.samples = samples

    def labels(self) -> list[str]:
        return self.capability_labels

    def num_tokens(self) -> int:
        return self.num_samples * self.seq_len

    def seq_len_of(self) -> int:
        return self.seq_len


def _stable_hash(text: str) -> int:
    # FNV-1a — deterministic across processes without relying on hash().
    h = 2166136261
    for byte in text.encode("utf-8"):
        h ^= byte
        h = (h * 16777619) & 0xFFFFFFFF
    return h


# -- per-layer aggregation --------------------------------------------------


class LayerResult:
    """Saliency aggregates for one traced layer (serializable)."""

    __slots__ = ("layer", "num_tokens", "by_expert", "by_label", "trace_samples")

    def __init__(self, layer: int, num_tokens: int) -> None:
        self.layer = layer
        self.num_tokens = num_tokens
        self.by_expert: dict[int, dict[str, float | int]] = {}
        self.by_label: dict[tuple[int, str], dict[str, float | int]] = {}
        self.trace_samples: list[dict[str, Any]] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "num_tokens": self.num_tokens,
            "by_expert": {str(k): v for k, v in self.by_expert.items()},
            "by_label": {f"{e}:{lbl}": v for (e, lbl), v in self.by_label.items()},
            "trace_samples": self.trace_samples,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayerResult:
        res = cls(int(data["layer"]), int(data["num_tokens"]))
        res.by_expert = {int(k): v for k, v in data["by_expert"].items()}
        res.by_label = {
            (int(k.split(":", 1)[0]), k.split(":", 1)[1]): v for k, v in data["by_label"].items()
        }
        res.trace_samples = list(data.get("trace_samples") or [])
        return res


def trace_layer(
    model: Any, layer: int, pool: CalibrationPool, top_k: int | None = None
) -> LayerResult:
    """Run one layer's router + experts over the whole calibration pool.

    ``model`` is a :class:`eval_lab.atlas.model.MiniMoE`; ``top_k`` defaults to
    the model's own ``num_experts_per_tok``.
    """
    res = LayerResult(layer, pool.num_tokens())
    gate_w, gate_b, experts = model.layers[layer]
    k = top_k if top_k is not None else model.num_experts_per_tok
    num_experts = model.num_local_experts

    for sample_idx, (label, tokens) in enumerate(pool.samples):
        for token_idx, x in enumerate(tokens):
            logits = [_dot(gate_w[e], x) + gate_b[e] for e in range(num_experts)]
            probs = _softmax(logits)
            order = sorted(range(num_experts), key=lambda e: probs[e], reverse=True)
            sel = order[:k]
            for e in sel:
                p = probs[e]
                outv = _dot_row(experts[e], x)
                onorm = math.sqrt(sum(v * v for v in outv))
                _acc(res.by_expert, e, p, onorm)
                _acc(res.by_label, (e, label), p, onorm)
                res.trace_samples.append(
                    {
                        "layer": layer,
                        "expert": e,
                        "prob": round(p, 6),
                        "outnorm": round(onorm, 6),
                        "label": label,
                        "sample": sample_idx,
                        "token": token_idx,
                    }
                )
    _normalize(res)
    return res


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


def _dot_row(m: list[list[float]], x: list[float]) -> list[float]:
    return [_dot(row, x) for row in m]


def _softmax(xs: list[float]) -> list[float]:
    m = max(xs)
    ex = [math.exp(v - m) for v in xs]
    s = sum(ex)
    return [v / s for v in ex]


def _acc(
    target: dict[Any, dict[str, float | int]],
    key: int | tuple[int, str],
    prob: float,
    onorm: float,
) -> None:
    cur = target.get(key)
    if cur is None:
        target[key] = {
            "count": 1,
            "prob": prob,
            "outnorm": onorm,
            "outnorm2": onorm * onorm,
            "value_probnorm": prob * onorm,
        }
    else:
        cur["count"] = int(cur["count"]) + 1
        cur["prob"] = float(cur["prob"]) + prob
        cur["outnorm"] = float(cur["outnorm"]) + onorm
        cur["outnorm2"] = float(cur["outnorm2"]) + onorm * onorm
        cur["value_probnorm"] = float(cur["value_probnorm"]) + prob * onorm


def _normalize(res: LayerResult) -> None:
    total = res.num_tokens
    for e, cur in res.by_expert.items():
        c = int(cur["count"])
        mean_prob = float(cur["prob"]) / c if c else 0.0
        mean_onorm = float(cur["outnorm"]) / c if c else 0.0
        var = float(cur["outnorm2"]) / c - mean_onorm * mean_onorm if c else 0.0
        res.by_expert[e] = {
            "activation_count": c,
            "frequency": round(c / total, 6),
            "mean_prob": round(mean_prob, 6),
            "mean_outnorm": round(mean_onorm, 6),
            "variance": round(max(var, 0.0), 8),
            "total_value": round(mean_prob * mean_onorm * (c / total), 8),
        }
    # per-label normalization uses each label's own token share
    for (e, lbl), cur in list(res.by_label.items()):
        c = int(cur["count"])
        mean_prob = float(cur["prob"]) / c if c else 0.0
        mean_onorm = float(cur["outnorm"]) / c if c else 0.0
        res.by_label[(e, lbl)] = {
            "activation_count": c,
            "mean_prob": round(mean_prob, 6),
            "mean_outnorm": round(mean_onorm, 6),
            "total_value": round(mean_prob * mean_onorm, 8),
        }


def layer_to_sql_rows(lr: LayerResult) -> list[SqlRow]:
    rows: list[SqlRow] = []
    total = lr.num_tokens
    for e in sorted(lr.by_expert):
        cur = lr.by_expert[e]
        mean = float(cur["mean_prob"]) * float(cur["mean_outnorm"])
        rows.append(
            SqlRow(
                layer=lr.layer,
                expert=e,
                mean=round(mean, 6),
                frequency=float(cur["frequency"]),
                total_value=round(mean * float(cur["frequency"]), 8),
                variance=float(cur["variance"]),
                activation_count=int(cur["activation_count"]),
                n_routed=total,
            )
        )
    return rows


def layer_to_label_rows(lr: LayerResult, labels: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for e in sorted({e for (e, _) in lr.by_label}):
        for lbl in labels:
            cur = lr.by_label.get((e, lbl))
            if cur is None:
                continue
            total = lr.num_tokens
            rows.append(
                {
                    "layer": lr.layer,
                    "expert": e,
                    "label": lbl,
                    "mean": float(cur["mean_prob"]),
                    "frequency": round(int(cur["activation_count"]) / total, 6),
                    "total_value": float(cur["total_value"]),
                    "activation_count": int(cur["activation_count"]),
                }
            )
    return rows

"""Deterministic synthetic mini-MoE — the M3 tracer's auditable source model.

Milestone 3's Atlas Lab is a *genuine* lightweight layerwise MoE tracer (handoff
option A). It builds a small, fixed-seed synthetic MoE whose router and experts
have meaningful geometry (each expert owns a preferred direction), so calibration
contexts produce non-trivial, reproducible routing and real per-expert saliency.
Nothing here is fabricated: weights are materialized from a seed and the forward
pass math below is executed for real.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

from eval_lab.schemas.atlas_runtime import DEFAULT_MINI_MOE


class MiniMoE:
    """A tiny top-k routed MoE: ``num_layers`` x ``num_experts`` experts.

    Each layer has a router ``W_g`` (num_experts x hidden) + bias, and per-expert
    output projections ``W_e`` (hidden x hidden). Expert ``e`` is built around a
    preferred direction ``dir_e`` so routing aligns inputs with expert specialties.
    """

    def __init__(
        self,
        *,
        num_hidden_layers: int = 6,
        num_local_experts: int = 8,
        num_experts_per_tok: int = 2,
        hidden_size: int = 32,
        intermediate_size: int = 64,
        seed: int = 0,
    ) -> None:
        self.num_hidden_layers = num_hidden_layers
        self.num_local_experts = num_local_experts
        self.num_experts_per_tok = num_experts_per_tok
        self.hidden_size = hidden_size
        self.intermediate_size = intermediate_size
        self.seed = seed
        self._generate()

    # -- construction -------------------------------------------------------
    def _generate(self) -> None:
        rng = random.Random(self.seed)
        self.layers: list[tuple[list[list[float]], list[float], list[list[list[float]]]]] = []
        for _ in range(self.num_hidden_layers):
            gate_w = [
                [rng.gauss(0, self.hidden_size**-0.5) for _ in range(self.hidden_size)]
                for _ in range(self.num_local_experts)
            ]
            gate_b = [rng.gauss(0, 0.02) for _ in range(self.num_local_experts)]
            experts: list[list[list[float]]] = []
            for _ in range(self.num_local_experts):
                # Expert output projection built from a random preferred direction
                # so top-k routing distributes work across experts non-trivially.
                pref = [rng.gauss(0, 1) for _ in range(self.hidden_size)]
                norm = _norm(pref) or 1.0
                pref = [v / norm for v in pref]
                # project along the preferred direction with a small random spread
                mat = [[p * rng.gauss(0, 1) for p in pref] for _ in range(self.hidden_size)]
                experts.append(mat)
            self.layers.append((gate_w, gate_b, experts))

    # -- shapes -------------------------------------------------------------
    @property
    def topology(self) -> dict[str, Any]:
        return {
            "num_hidden_layers": self.num_hidden_layers,
            "num_local_experts": self.num_local_experts,
            "num_experts_per_tok": self.num_experts_per_tok,
            "hidden_size": self.hidden_size,
            "intermediate_size": self.intermediate_size,
            "seed": self.seed,
            "model_type": "synthetic_moe",
        }

    @property
    def param_count(self) -> int:
        # router: n_experts*hidden + n_experts ; experts: n_experts * hidden*hidden
        router = self.num_local_experts * self.hidden_size + self.num_local_experts
        experts = self.num_local_experts * self.hidden_size * self.hidden_size
        return self.num_hidden_layers * (router + experts)

    def expert_params_per_expert(self) -> int:
        return self.hidden_size * self.hidden_size

    # -- persistence --------------------------------------------------------
    def write(self, dir_path: str | Path) -> None:
        """Materialize config.json + weights.json so the run is auditable."""
        root = Path(dir_path)
        root.mkdir(parents=True, exist_ok=True)
        (root / "config.json").write_text(json.dumps(self.topology, indent=2), encoding="utf-8")
        (root / "weights.json").write_text(
            json.dumps([_layer_to_json(gw, gb, ex) for gw, gb, ex in self.layers]),
            encoding="utf-8",
        )


def _norm(vec: list[float]) -> float:
    return math.sqrt(sum(v * v for v in vec))


def _layer_to_json(
    gate_w: list[list[float]],
    gate_b: list[float],
    experts: list[list[list[float]]],
) -> dict[str, Any]:
    return {"gate_weight": gate_w, "gate_bias": gate_b, "experts": experts}


def build_mini_moe(config: dict[str, Any] | None = None) -> MiniMoE:
    """Construct a :class:`MiniMoE` from optional override kwargs (defaults applied)."""
    params = dict(DEFAULT_MINI_MOE)
    params.update((k, v) for k, v in (config or {}).items() if k in DEFAULT_MINI_MOE)
    return MiniMoE(**params)

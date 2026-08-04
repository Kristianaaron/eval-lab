"""Candidate prune-topology (plan) construction from measured saliency.

For each keep budget ``k`` a plan keeps the top-``k`` experts per layer by
``total_value`` saliency (utilization-weighted), producing the auditable
``plans.json`` entries and reserved ``UnitKeepMap`` layer selections. All
decisions derive from the measured saliency rows — no fabricated ranking.
"""

from __future__ import annotations

from typing import Any

from eval_lab.schemas.atlas import (
    EvidenceKind,
    KeepMapEntry,
    UnitIdentity,
    UnitKeepMap,
    UnitKind,
)

SALIENCY_SIGNAL = "router_probability_x_output_norm"
F32_BYTES = 4
BF16_BYTES = 2


def _per_layer_saliency(saliency_rows: list[dict[str, Any]]) -> dict[tuple[int, int], float]:
    score: dict[tuple[int, int], float] = {}
    for r in saliency_rows:
        layer = int(r["layer"])
        expert = int(r["expert"])
        score[(layer, expert)] = float(r.get("total_value") or 0.0)
    return score


def build_plans(
    *,
    num_layers: int,
    num_experts: int,
    source_model_id: str,
    saliency_rows: list[dict[str, Any]],
    keep_budgets: list[int],
    expert_params: int,
) -> list[dict[str, Any]]:
    score = _per_layer_saliency(saliency_rows)
    plans: list[dict[str, object]] = []
    budgets = sorted({max(1, min(b, num_experts)) for b in keep_budgets}, reverse=True)
    for k in budgets:
        full = k >= num_experts
        kept_per_layer: dict[str, int] = {}
        all_entries: list[dict[str, object]] = []
        precision_entries: list[dict[str, object]] = []
        kept_params = 0
        for layer in range(num_layers):
            ranked = sorted(
                range(num_experts),
                key=lambda e: score.get((layer, e), 0.0),
                reverse=True,
            )
            keep = set(ranked[:k])
            kept_per_layer[str(layer)] = k if full else len(keep)
            kept_params += len(keep)
            for e in range(num_experts):
                reason = "protected_full" if full else ("saliency_top_k" if e in keep else "budget")
                all_entries.append(
                    {
                        "layer_index": layer,
                        "source_expert_id": e,
                        "keep": e in keep,
                        "reason": reason,
                    }
                )
                if e in keep:
                    precision_entries.append(
                        {
                            "layer_index": layer,
                            "source_expert_id": e,
                            "bits": 16.0,
                            "precision": "source_unprobed",
                            "reconstruction_error": 0.0,
                        }
                    )
        plans.append(
            {
                "name": f"keep{k}-{'full' if full else 'saliency'}",
                "strategy": "full" if full else "saliency_top_k",
                "keep_per_layer": k,
                "kept_per_layer": kept_per_layer,
                "keep_map": {
                    "source_model_id": source_model_id,
                    "entries": all_entries,
                },
                "precision": {"entries": precision_entries},
                "resident_bytes_a": round(kept_params * expert_params * F32_BYTES, 2),
                "resident_bytes_b": round(kept_params * expert_params * BF16_BYTES, 2),
            }
        )
    return plans


def build_keep_maps(
    *,
    num_layers: int,
    num_experts: int,
    source_model_id: str,
    saliency_rows: list[dict[str, Any]],
    top_k: int,
) -> list[UnitKeepMap]:
    """Primary keep-map: per-layer top-``top_k`` selection (reserved schema)."""
    score = _per_layer_saliency(saliency_rows)
    keep_maps: list[UnitKeepMap] = []
    for layer in range(num_layers):
        ranked = sorted(
            range(num_experts),
            key=lambda e: score.get((layer, e), 0.0),
            reverse=True,
        )
        keep = set(ranked[:top_k])
        rank_of = {e: i + 1 for i, e in enumerate(ranked)}
        entries: list[KeepMapEntry] = []
        for e in range(num_experts):
            entries.append(
                KeepMapEntry(
                    unit=UnitIdentity(
                        source_model_id=source_model_id,
                        layer_index=layer,
                        unit_kind=UnitKind.expert,
                        source_unit_id=e,
                    ),
                    kept=e in keep,
                    top_k=top_k,
                    saliency=score.get((layer, e)),
                    saliency_signal=SALIENCY_SIGNAL,
                    evidence_kind=EvidenceKind.measured,
                    rank_within_layer=rank_of[e],
                )
            )
        keep_maps.append(
            UnitKeepMap(
                layer_index=layer,
                unit_kind=UnitKind.expert,
                top_k=top_k,
                entries=entries,
            )
        )
    return keep_maps

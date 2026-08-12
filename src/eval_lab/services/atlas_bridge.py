"""atlas-bridge consumer (eval-lab side of the cross-repo manifest bridge).

Discovers ``atlas_runs/<id>/run_manifest.json`` dirs produced by the model-atlas
``export`` command, validates them against the reserved atlas schemas
(``UnitKeepMap`` / ``UnitIdentity``/ ``EvidenceKind`` in ``schemas/atlas.py``),
persists an import record (idempotent), and registers any derivative checkpoint
as a model asset. eval-lab never imports ``model_atlas``; files are hand-authored
or produced by the sibling engine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval_lab.schemas.atlas import EvidenceKind, KeepMapEntry, UnitIdentity, UnitKeepMap, UnitKind
from eval_lab.schemas.atlas_bridge import AtlasBridgeImport, AtlasPlanImport
from eval_lab.schemas.model_asset import ModelAssetRecord, ModelAssetType, ValidationState
from eval_lab.services.models import ModelAssetService
from eval_lab.storage.atlas_imports import AtlasImportStore

_CORE_FILES = ("run_manifest.json", "layer_saliency.json", "plans.json")


class AtlasBridgeService:
    def __init__(
        self,
        out_root: str | Path,
        *,
        models_root: str | Path | None = None,
    ) -> None:
        self.out_root = Path(out_root)
        self.runs_dir = self.out_root / "atlas_runs"
        self.store = AtlasImportStore(self.runs_dir)
        if models_root is None:
            models_root = self.out_root.parent / "models"
        self._models = ModelAssetService(models_root)

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def scan(self) -> list[AtlasBridgeImport]:
        """Discover atlas runs: persisted imports plus manifest-only dirs."""
        out: list[AtlasBridgeImport] = []
        for mf in sorted(self.runs_dir.glob("*/run_manifest.json")):
            run_id = mf.parent.name
            rec = self.store.get(run_id)
            if rec is not None:
                out.append(rec)
                continue
            manifest = _read_json(mf) or {}
            out.append(self._from_manifest_only(run_id, manifest))
        return out

    def import_run(self, run_id: str) -> AtlasBridgeImport:
        """Read/validate/persist a run; re-import of the same id is a no-op."""
        run_dir = self.run_dir(run_id)
        if not (run_dir / "run_manifest.json").is_file():
            raise FileNotFoundError(f"atlas run dir missing: {run_dir}")

        existing = self.store.get(run_id)
        if existing is not None:
            return existing

        manifest = _read_json(run_dir / "run_manifest.json") or {}
        saliency = _read_json(run_dir / "layer_saliency.json") or []
        plans = _read_json(run_dir / "plans.json") or []
        derivative = _read_json(run_dir / "derivative.json")
        planning = _read_json(run_dir / "planning_maps.json") or {}
        record = self._build_record(run_id, manifest, saliency, plans, derivative, planning)
        self.store.save(record)
        if derivative is not None:
            self._register_derivative(run_id, record)
        return record

    def get_import(self, run_id: str) -> AtlasBridgeImport | None:
        return self.store.get(run_id)

    # -- record construction ------------------------------------------------
    def _from_manifest_only(self, run_id: str, manifest: dict[str, Any]) -> AtlasBridgeImport:
        planning = _read_json(self.run_dir(run_id) / "planning_maps.json") or {}
        return AtlasBridgeImport(
            run_id=run_id,
            arch=manifest.get("source_arch"),
            status=manifest.get("status"),
            n_tasks=manifest.get("n_tasks"),
            n_plans=0,
            evidence_present=manifest.get("evidence_present") or [],
            has_derivative=self.run_dir(run_id).joinpath("derivative.json").is_file(),
            manifest=manifest,
            maps=planning.get("maps") or {},
            real_bytes=planning or None,
        )

    def _build_record(
        self,
        run_id: str,
        manifest: dict[str, Any],
        saliency: list[dict[str, Any]],
        plans: list[dict[str, Any]],
        derivative: dict[str, Any] | None,
        planning: dict[str, Any] | None = None,
    ) -> AtlasBridgeImport:
        sal_lookup = {
            (int(r["layer"]), int(r["expert"])): r
            for r in saliency
            if "layer" in r and "expert" in r
        }
        fallback_source = manifest.get("source_arch") or "atlas"
        plan_imports = [self._plan_to_import(p, sal_lookup, fallback_source) for p in plans]
        planning = planning or {}
        return AtlasBridgeImport(
            run_id=run_id,
            arch=manifest.get("source_arch"),
            status=manifest.get("status"),
            n_tasks=manifest.get("n_tasks"),
            n_plans=len(plans),
            evidence_present=manifest.get("evidence_present") or [],
            has_derivative=derivative is not None,
            manifest=manifest,
            saliency=saliency,
            plans=plan_imports,
            derivative=derivative,
            maps=planning.get("maps") or {},
            real_bytes=(
                {"schema_version": planning.get("schema_version"),
                 "source_arch": planning.get("source_arch"),
                 "candidates": planning.get("candidates") or []}
                if planning
                else None
            ),
        )

    def _plan_to_import(
        self,
        plan: dict[str, Any],
        sal_lookup: dict[tuple[int, int], dict[str, Any]],
        fallback_source: str,
    ) -> AtlasPlanImport:
        keep_map = plan.get("keep_map") or {}
        entries = keep_map.get("entries") or []
        kept_per_layer = plan.get("kept_per_layer") or {}
        source_model_id = keep_map.get("source_model_id") or fallback_source

        by_layer: dict[int, list[KeepMapEntry]] = {}
        for e in entries:
            layer = int(e["layer_index"])
            expert = int(e["source_expert_id"])
            sal = sal_lookup.get((layer, expert))
            by_layer.setdefault(layer, []).append(
                KeepMapEntry(
                    unit=UnitIdentity(
                        source_model_id=source_model_id,
                        layer_index=layer,
                        unit_kind=UnitKind.expert,
                        source_unit_id=expert,
                    ),
                    kept=bool(e.get("keep", True)),
                    top_k=int(kept_per_layer.get(str(layer), 0)),
                    saliency=float(sal["mean"]) if sal is not None else None,
                    evidence_kind=EvidenceKind.measured,
                )
            )

        keep_maps = [
            UnitKeepMap(
                layer_index=layer,
                unit_kind=UnitKind.expert,
                top_k=int(kept_per_layer.get(str(layer), 0)),
                entries=layer_entries,
            )
            for layer, layer_entries in sorted(by_layer.items())
        ]
        return AtlasPlanImport(
            name=plan.get("name", "plan"),
            strategy=plan.get("strategy"),
            keep_per_layer=plan.get("keep_per_layer"),
            kept_per_layer=kept_per_layer,
            keep_maps=keep_maps,
            precision=[dict(e) for e in (plan.get("precision") or {}).get("entries", [])],
            resident_bytes_a=plan.get("resident_bytes_a"),
            resident_bytes_b=plan.get("resident_bytes_b"),
            coverage=_coverage(entries),
        )

    # -- derivative registration --------------------------------------------
    def _register_derivative(
        self, run_id: str, record: AtlasBridgeImport
    ) -> ModelAssetRecord | None:
        deriv = record.derivative
        if deriv is None:
            return None
        asset_id = deriv.get("model_asset_id")
        existing = self._models.store.get(asset_id) if asset_id else None
        if existing is not None:
            return existing
        asset = ModelAssetRecord(
            asset_id=asset_id or self._models.store.new_id("deriv"),
            name=deriv.get("display_name") or f"atlas-run {run_id} derivative",
            asset_type=ModelAssetType.derivative_checkpoint,
            path=deriv.get("checkpoint_path"),
            family=deriv.get("model_family"),
            architecture=deriv.get("architecture"),
            param_metadata={
                "kept_per_layer": deriv.get("kept_per_layer") or {},
                "identity_source_slots": deriv.get("identity_source_slots") or {},
            },
            stored_size_bytes=deriv.get("stored_size_bytes"),
            resident_estimate_bytes=deriv.get("estimated_resident_bytes"),
            runnable=False,
            atlas_compatible=False,
            validation_state=ValidationState.unvalidated,
            parent_asset_id=deriv.get("parent_model_id"),
            source_experiment_id=deriv.get("source_experiment_id"),
            source_atlas_run_id=run_id,
            tags=["atlas-derivative"],
        )
        self._models.store.save(asset)
        return asset


def _read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _coverage(entries: list[dict[str, Any]]) -> float | None:
    """Fraction of keep-map entries that are kept (None when not measurable)."""
    if not entries:
        return None
    kept = sum(1 for e in entries if bool(e.get("keep", True)))
    return round(kept / len(entries), 4)

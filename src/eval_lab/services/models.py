"""Typed application service layer (spec 11) — model assets for Milestone 1.

View components and routes consume these typed methods; they never touch
persistence or checkpoint internals directly. ``resolve_available_actions`` is
a pure function driven by the asset record + environment budget so the GUI
renders only the valid operation for each asset (spec 3.4, 14.1).
"""

from __future__ import annotations

from pathlib import Path

from eval_lab.inspection.checkpoint import inspect_checkpoint
from eval_lab.schemas.model_asset import (
    ActionEligibility,
    AvailableAction,
    CheckpointInspection,
    EnvBudget,
    ModelAssetRecord,
    ModelAssetType,
    ValidationState,
)
from eval_lab.storage.model_assets import ModelAssetStore

_GIB = 1024**3


def resolve_available_actions(
    asset: ModelAssetRecord,
    budget: EnvBudget | None = None,
) -> dict[str, AvailableAction]:
    """Compute which operations are valid for ``asset`` and why (spec 3.4)."""
    budget = budget or EnvBudget()
    resid_mem_gb = (asset.resident_estimate_bytes or 0) / _GIB
    resident_fits = (
        budget.resident_target_gb is not None and resid_mem_gb <= budget.resident_target_gb
    )

    is_local = asset.path and Path(asset.path).is_dir()

    # Inspect checkpoint requires a local path (endpoints are not inspectable dirs).
    inspect = AvailableAction(available=bool(is_local))
    if not is_local:
        inspect.reason = "No local checkpoint path to inspect (endpoint asset)."

    runnable_type = asset.asset_type in (
        ModelAssetType.runnable_local,
        ModelAssetType.remote_endpoint,
        ModelAssetType.hosted_teacher,
    )
    evaluate = AvailableAction(available=bool(asset.runnable or runnable_type or resident_fits))
    if not evaluate.available:
        evaluate.reason = (
            "Direct evaluation is unavailable because no runnable endpoint is "
            "configured and the checkpoint exceeds the current memory budget."
        )

    build_atlas = AvailableAction(
        available=asset.asset_type == ModelAssetType.source_checkpoint
        and bool(asset.atlas_compatible)
    )
    if not build_atlas.available:
        if asset.asset_type != ModelAssetType.source_checkpoint:
            build_atlas.reason = "Only a source checkpoint can be analysed layerwise."
        else:
            build_atlas.reason = (
                "Checkpoint is not layerwise-compatible (missing sparse/MOE config or shards)."
            )

    has_atlas = bool(asset.source_atlas_run_id or budget.has_completed_atlas)
    keep_map = AvailableAction(available=has_atlas)
    if not keep_map.available:
        keep_map.reason = "No completed atlas run is attached."
    experiment = AvailableAction(
        available=has_atlas or asset.asset_type == ModelAssetType.derivative_checkpoint
    )
    if not experiment.available:
        experiment.reason = (
            "Experiments are derived from a completed atlas or an existing derivative."
        )

    compare = AvailableAction(available=budget.has_completed_eval)
    if not compare.available:
        compare.reason = "No completed evaluation run exists."

    return {
        "inspect_checkpoint": inspect,
        "evaluate_directly": evaluate,
        "build_atlas": build_atlas,
        "create_keep_map": keep_map,
        "create_experiment": experiment,
        "compare": compare,
    }


class ModelAssetService:
    def __init__(self, store_root: str | Path) -> None:
        self.store = ModelAssetStore(store_root)

    # -- registration -------------------------------------------------------
    def register_local_checkpoint(
        self,
        path: str | Path,
        *,
        name: str | None = None,
        asset_id: str | None = None,
        memory_gb: float = 256.0,
    ) -> tuple[ModelAssetRecord, CheckpointInspection]:
        """Inspect a local directory and register it as a source/runnable asset."""
        inspection = inspect_checkpoint(path, memory_gb=memory_gb)
        asset_type = (
            ModelAssetType.source_checkpoint
            if inspection.atlas_compatible
            else ModelAssetType.runnable_local
        )
        record = ModelAssetRecord(
            asset_id=asset_id or self.store.new_id(asset_type.value),
            name=name or Path(path).name,
            asset_type=asset_type,
            path=str(Path(path)),
            architecture=inspection.architecture,
            revision="unknown",
            quantization_format=inspection.quantization_format,
            param_metadata={
                "model_type": inspection.model_type,
                "num_hidden_layers": inspection.num_hidden_layers,
                "num_local_experts": inspection.num_local_experts,
                "num_experts_per_tok": inspection.num_experts_per_tok,
                "params_estimate": inspection.params_estimate,
            },
            stored_size_bytes=inspection.stored_size_bytes,
            resident_estimate_bytes=inspection.resident_estimate_bytes,
            runnable=inspection.runnable_here,
            atlas_compatible=inspection.atlas_compatible,
            validation_state=(
                ValidationState.valid if inspection.valid else ValidationState.invalid
            ),
            warnings=[i.message for i in inspection.issues if i.level == "warning"],
        )
        self.store.save(record)
        return record, inspection

    def register_asset(self, record: ModelAssetRecord) -> ModelAssetRecord:
        return self.store.save(record)

    # -- queries ------------------------------------------------------------
    def get_model_asset(self, asset_id: str) -> ModelAssetRecord | None:
        return self.store.get(asset_id)

    def list_model_assets(self) -> list[ModelAssetRecord]:
        return sorted(self.store.list(), key=lambda a: a.registered_at, reverse=True)

    def delete_model_asset(self, asset_id: str) -> bool:
        return self.store.delete(asset_id)

    def eligibility(
        self, asset: ModelAssetRecord, budget: EnvBudget | None = None
    ) -> ActionEligibility:
        actions = resolve_available_actions(asset, budget)
        return ActionEligibility(asset_id=asset.asset_id, actions=actions)


def seed_fixtures(store_root: str | Path) -> list[ModelAssetRecord]:
    """Seed synthetic model assets (spec 15.14): no real Kimi K3 required in CI."""
    service = ModelAssetService(store_root)
    existing = {a.asset_id for a in service.list_model_assets()}
    fixtures: list[ModelAssetRecord] = [
        ModelAssetRecord(
            asset_id="kimi-k3-official",
            name="Kimi K3",
            asset_type=ModelAssetType.source_checkpoint,
            path="/models/Kimi-K3",
            family="Moonshot",
            architecture="KimiK3ForCausalLM",
            revision="official",
            quantization_format="MXFP4",
            param_metadata={
                "num_hidden_layers": 93,
                "num_local_experts": 896,
                "num_experts_per_tok": 16,
            },
            stored_size_bytes=int(1.56 * 1024**4),
            resident_estimate_bytes=int(1.5 * 1024**4),
            runnable=False,
            atlas_compatible=True,
            validation_state=ValidationState.valid,
            tags=["oversized", "source"],
            warnings=["Checkpoint exceeds resident-memory envelope; direct load unavailable."],
        ),
        ModelAssetRecord(
            asset_id="deepseek-v4-flash",
            name="DeepSeek V4 Flash",
            asset_type=ModelAssetType.remote_endpoint,
            family="DeepSeek",
            revision="0731",
            quantization_format="NVFP4",
            runnable=True,
            validation_state=ValidationState.valid,
            tags=["baseline", "reference"],
            latest_quality_score=0.82,
        ),
        ModelAssetRecord(
            asset_id="qwen3.5-2b-vision",
            name="Qwen3.5 2B Vision",
            asset_type=ModelAssetType.runnable_local,
            family="Qwen",
            revision="2B-Q8_0",
            quantization_format="Q8_0",
            runnable=True,
            validation_state=ValidationState.valid,
            tags=["baseline", "small"],
            latest_quality_score=0.61,
        ),
        ModelAssetRecord(
            asset_id="k3-agent-96",
            name="K3 Agent 96",
            asset_type=ModelAssetType.derivative_checkpoint,
            family="Moonshot",
            architecture="K3Agent96",
            revision="agent-v2",
            quantization_format="MXFP4/INT3",
            stored_size_bytes=int(211 * 1024**3),
            parent_asset_id="kimi-k3-official",
            runnable=True,
            atlas_compatible=False,
            validation_state=ValidationState.valid,
            tags=["derivative"],
            latest_quality_score=0.78,
            notes="96 retained experts/layer from keep map (synthetic fixture).",
        ),
    ]
    for record in fixtures:
        if record.asset_id not in existing:
            service.register_asset(record)
    return service.list_model_assets()

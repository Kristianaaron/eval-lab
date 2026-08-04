"""Experiment service (Milestone 5).

Wraps the experiment store behind a typed service and derives experiments from
imported atlas runs: a user pins one candidate plan from an imported run's
``plans.json`` as a named experiment, and the service records the keep-map
scope, links any derivative model asset built for that run, and tracks status.
The GUI (and any runner flow) never touches the store or json directly.
"""

from __future__ import annotations

from pathlib import Path

from eval_lab.schemas.experiment import ExperimentRecord, ExperimentStatus, ExperimentType
from eval_lab.schemas.model_asset import ModelAssetType
from eval_lab.services.atlas_bridge import AtlasBridgeService
from eval_lab.storage.experiments import ExperimentStore
from eval_lab.storage.model_assets import ModelAssetStore


class ExperimentService:
    def __init__(
        self,
        bridge: AtlasBridgeService,
        root: str | Path,
        *,
        models_store: ModelAssetStore | None = None,
    ) -> None:
        self.bridge = bridge
        self.store = ExperimentStore(root)
        self._models = models_store

    def create_from_plan(
        self,
        run_id: str,
        plan_name: str,
        *,
        objective: str = "",
        memory_target_bytes: int | None = None,
        experiment_type: ExperimentType = ExperimentType.keep_map,
        status: ExperimentStatus = ExperimentStatus.draft,
    ) -> ExperimentRecord:
        """Create an experiment pinned to ``plan_name`` of imported run ``run_id``.

        Raises FileNotFoundError when the run has no imported record, or
        ValueError when ``plan_name`` does not match a candidate plan.
        """
        imp = self.bridge.get_import(run_id)
        if imp is None:
            raise FileNotFoundError(f"atlas import not found: {run_id}")
        plan = next((p for p in imp.plans if p.name == plan_name), None)
        if plan is None:
            raise ValueError(
                f"plan '{plan_name}' not found in run {run_id} (have: "
                + ", ".join(p.name for p in imp.plans)
                + ")"
            )
        kept_per_layer = dict(plan.kept_per_layer or {})
        total_kept = (
            sum(kept_per_layer.values())
            if kept_per_layer
            else sum(km.kept_count for km in plan.keep_maps)
        )

        derivative_id, source_id = self._links_for_run(run_id)
        record = ExperimentRecord(
            experiment_id=self.store.new_id(),
            experiment_type=experiment_type,
            run_id=run_id,
            plan_name=plan.name,
            objective=objective,
            memory_target_bytes=memory_target_bytes,
            kept_per_layer=kept_per_layer,
            total_kept=total_kept,
            derivate_asset_id=derivative_id,
            source_asset_id=source_id,
            status=status,
        )
        return self.store.save(record)

    def _links_for_run(self, run_id: str) -> tuple[str | None, str | None]:
        """Find the derivative + source model assets registered for a run."""
        if self._models is None:
            return None, None
        derivative_id: str | None = None
        source_id: str | None = None
        for asset in self._models.list():
            if asset.source_atlas_run_id != run_id:
                continue
            if asset.asset_type == ModelAssetType.derivative_checkpoint:
                derivative_id = asset.asset_id
                source_id = asset.parent_asset_id
        return derivative_id, source_id

    def list(self) -> list[ExperimentRecord]:
        return self.store.list()

    def get(self, experiment_id: str) -> ExperimentRecord | None:
        return self.store.get(experiment_id)

    def delete(self, experiment_id: str) -> bool:
        return self.store.delete(experiment_id)

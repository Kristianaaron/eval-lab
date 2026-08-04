"""Atlas Lab runtime service (Milestone 3, option A — genuine lightweight tracer).

Builds a small deterministic synthetic MoE, runs a real CPU layerwise
router/expert forward pass over deterministic calibration contexts, and persists
genuinely-measured per-layer/per-expert saliency as the reserved atlas artifacts
(``atlas_out/atlas_runs/<id>/``) that the atlas-bridge consumer imports. The
trace runs as a restart-safe orchestrator job with per-layer progress,
pause/resume/cancel and recovery checkpoints, and on completion links the
artifacts back to the source model asset and calibration suite.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval_lab.atlas.model import build_mini_moe
from eval_lab.atlas.plans import build_keep_maps, build_plans
from eval_lab.atlas.store import AtlasRunStore
from eval_lab.atlas.tracer import (
    CalibrationPool,
    LayerResult,
    layer_to_label_rows,
    layer_to_sql_rows,
    trace_layer,
)
from eval_lab.schemas.atlas import EvidenceLevel, UnitKeepMap
from eval_lab.schemas.atlas_runtime import (
    DEFAULT_KEEP_BUDGETS,
    TRACE_DEPTH_PARAMS,
    AtlasBuildConfig,
    AtlasPlanPreview,
    AtlasRunDetail,
    ResourceEstimate,
    SqlRow,
)
from eval_lab.schemas.job import Job, JobResult, JobState
from eval_lab.services.orchestrator import Executor, JobContext, JobOrchestrator
from eval_lab.storage.model_assets import ModelAssetStore
from eval_lab.tasks.loader import load_suite_yaml

DEFAULT_CAPABILITY_LABELS = [
    "code_generation",
    "mathematical_reasoning",
    "planning",
    "tool_selection",
    "long_context_retrieval",
    "spatial_reasoning",
]
_FINALIZE_OVERHEAD_S = 0.05
_FINALIZE_MULTIPLIER = 1.6


def _resolve_moe_params(cfg: AtlasBuildConfig) -> dict[str, int]:
    return {
        "num_hidden_layers": cfg.num_hidden_layers if cfg.num_hidden_layers is not None else 6,
        "num_local_experts": cfg.num_local_experts if cfg.num_local_experts is not None else 8,
        "num_experts_per_tok": cfg.num_experts_per_tok
        if cfg.num_experts_per_tok is not None
        else 2,
        "hidden_size": cfg.hidden_size if cfg.hidden_size is not None else 32,
        "intermediate_size": cfg.intermediate_size if cfg.intermediate_size is not None else 64,
        "seed": cfg.seed,
    }


class AtlasRuntimeService:
    """Typed service binding the M3 tracer to the shared orchestrator + wizard API."""

    def __init__(
        self,
        orchestrator: JobOrchestrator,
        out_root: str | Path,
        *,
        models_store: ModelAssetStore,
        suites_dir: str | Path = "configs/suites",
    ) -> None:
        self.orchestrator = orchestrator
        self.store = AtlasRunStore(out_root)
        self.models_store = models_store
        self.suites_dir = str(suites_dir)
        self.orchestrator.register(
            "atlas", make_atlas_executor(out_root=out_root, models_store=models_store)
        )

    # -- wizard -------------------------------------------------------------
    def estimate(self, cfg: AtlasBuildConfig) -> ResourceEstimate:
        params = _resolve_moe_params(cfg)
        n_samples, seq_len = TRACE_DEPTH_PARAMS[cfg.trace_depth]
        num_tokens = n_samples * seq_len
        labels = cfg.capability_labels or DEFAULT_CAPABILITY_LABELS
        model = build_mini_moe(params)
        k = params["num_experts_per_tok"]
        # Probe one layer over a tiny pool to calibrate wall time honestly.
        probe = CalibrationPool(
            num_samples=2,
            seq_len=2,
            hidden_size=params["hidden_size"],
            capability_labels=labels,
            seed=cfg.seed,
        )
        t0 = time.perf_counter()
        trace_layer(model, 0, probe)
        dt = time.perf_counter() - t0
        per_token_layer = dt / probe.num_tokens()
        est_s = (
            per_token_layer * num_tokens * params["num_hidden_layers"] * _FINALIZE_MULTIPLIER
            + _FINALIZE_OVERHEAD_S
        )
        router_ops = params["num_local_experts"] * params["hidden_size"] * 2
        expert_ops = k * params["hidden_size"] * params["hidden_size"] * 2
        ops = num_tokens * params["num_hidden_layers"] * (router_ops + expert_ops)
        return ResourceEstimate(
            num_layers=params["num_hidden_layers"],
            num_experts=params["num_local_experts"],
            top_k=k,
            num_samples=n_samples,
            seq_len=seq_len,
            num_tokens=num_tokens,
            estimated_ops=round(ops, 2),
            estimated_wall_s=round(est_s, 4),
            mini_moe_params=model.param_count,
            mini_moe_resident_bytes=model.param_count * 4,
            trace_bytes=num_tokens * 160
            + params["num_hidden_layers"] * params["num_local_experts"] * len(labels) * 200,
            methodology=(
                "synthetic mini-MoE layerwise forward over deterministic calibration "
                "contexts; wall time calibrated from a one-layer probe."
            ),
        )

    # -- job lifecycle ------------------------------------------------------
    def launch(self, cfg: AtlasBuildConfig, *, name: str | None = None) -> Job:
        data = cfg.model_dump(mode="json")
        data["atlas_run_id"] = self.orchestrator.store.new_id("atlas")
        return self.orchestrator.submit(
            "atlas", data, name=name or f"build-atlas {cfg.model_asset_id}"
        )

    def get(self, job_id: str) -> Job | None:
        return self.orchestrator.get(job_id)

    def list_jobs(self) -> list[Job]:
        return self.orchestrator.list(kind="atlas")

    def cancel(self, job_id: str) -> Job | None:
        return self.orchestrator.cancel(job_id)

    def pause(self, job_id: str) -> Job | None:
        return self.orchestrator.pause(job_id)

    def resume(self, job_id: str) -> Job | None:
        return self.orchestrator.resume(job_id)

    def get_by_run(self, run_id: str) -> Job | None:
        for job in self.list_jobs():
            if job.config.get("atlas_run_id") == run_id:
                return job
        return None

    # -- run detail ---------------------------------------------------------
    def list_runs(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for mf in sorted(self.store.runs_dir.glob("*/run_manifest.json")):
            run_id = mf.parent.name
            man = _read_json(mf) or {}
            out.append(
                {
                    "atlas_run_id": run_id,
                    "status": man.get("status"),
                    "source_arch": man.get("source_arch"),
                    "source_checkpoint_id": man.get("source_checkpoint_id"),
                    "calibration_suite_id": man.get("calibration_suite_id"),
                    "n_tasks": man.get("n_tasks"),
                    "n_plans": _file_len(mf.parent / "plans.json"),
                    "evidence_present": man.get("evidence_present") or [],
                    "created_at": man.get("created_at"),
                    "completed_at": man.get("completed_at"),
                    "resumed_layer": self.store.load_last_layer(run_id),
                }
            )
        return sorted(out, key=lambda r: r.get("created_at") or "", reverse=True)

    def run_detail(self, run_id: str) -> AtlasRunDetail | None:
        run_dir = self.store.run_dir(run_id)
        man = _read_json(run_dir / "run_manifest.json")
        if man is None:
            return None
        saliency: list[SqlRow] = [
            SqlRow.model_validate(r) for r in (_read_json(run_dir / "layer_saliency.json") or [])
        ]
        plans: list[AtlasPlanPreview] = [
            AtlasPlanPreview.model_validate(
                {
                    "name": p.get("name"),
                    "strategy": p.get("strategy"),
                    "keep_per_layer": p.get("keep_per_layer"),
                    "kept_per_layer": p.get("kept_per_layer") or {},
                    "resident_bytes_a": p.get("resident_bytes_a") or 0.0,
                    "resident_bytes_b": p.get("resident_bytes_b") or 0.0,
                }
            )
            for p in (_read_json(run_dir / "plans.json") or [])
        ]
        keep_maps: list[UnitKeepMap] = [
            UnitKeepMap.model_validate(km) for km in (_read_json(run_dir / "keep_maps.json") or [])
        ]
        trace_count = _jsonl_len(run_dir / "trace.jsonl")
        return AtlasRunDetail(
            atlas_run_id=run_id,
            source_checkpoint_id=man.get("source_checkpoint_id") or "",
            calibration_suite_id=man.get("calibration_suite_id") or "",
            status=man.get("status") or "unknown",
            evidence_level=man.get("evidence_level") or EvidenceLevel.basic_saliency.value,
            evidence_present=man.get("evidence_present") or [],
            n_tasks=int(man.get("n_tasks") or 0),
            created_at=_parse_ts(man.get("created_at")),
            started_at=_parse_ts(man.get("started_at")),
            completed_at=_parse_ts(man.get("completed_at")),
            source_arch=man.get("source_arch"),
            topology=man.get("topology") or {},
            plans=plans,
            keep_maps=keep_maps,
            saliency=saliency,
            saliency_by_label=_read_json(run_dir / "saliency_by_label.json") or [],
            trace_count=trace_count,
            software_revision=man.get("software_revision"),
        )


def make_atlas_executor(*, out_root: str | Path, models_store: ModelAssetStore) -> Executor:
    store = AtlasRunStore(out_root)

    def executor(job: Job, ctx: JobContext) -> None:
        cfg = AtlasBuildConfig.model_validate(
            {k: v for k, v in job.config.items() if k != "atlas_run_id"}
        )
        run_id = job.config.get("atlas_run_id")
        if not run_id:
            raise ValueError("atlas job missing atlas_run_id")
        params = _resolve_moe_params(cfg)
        labels = cfg.capability_labels or DEFAULT_CAPABILITY_LABELS

        ctx.set_stage("loading_model")
        asset = models_store.get(cfg.model_asset_id)
        source_arch = asset.architecture if asset else None
        model = build_mini_moe(params)

        n_samples, seq_len = TRACE_DEPTH_PARAMS[cfg.trace_depth]
        pool = CalibrationPool(
            num_samples=n_samples,
            seq_len=seq_len,
            hidden_size=params["hidden_size"],
            capability_labels=labels,
            seed=cfg.seed,
        )

        ctx.set_stage("tracing_layers")
        last = store.load_last_layer(run_id) or -1
        results: list[LayerResult] = []
        if last >= 0:
            results = [r for r in store.load_layer_partials(run_id) if r.layer <= last]
        total = model.num_hidden_layers
        for layer in range(total):
            if layer <= last:
                continue
            if ctx.should_stop():
                # partial + checkpoint already saved for prior layers; nothing final yet.
                return
            ctx.set_progress(layer + 1, total, detail=f"layer {layer}")
            lr = trace_layer(model, layer, pool)
            store.save_layer_partial(run_id, lr)
            store.save_last_layer(run_id, layer)
            results.append(lr)

        ctx.set_progress(total, total, detail="finalizing")
        ctx.set_stage("aggregating_saliency")
        sql_rows = [r for lr in results for r in layer_to_sql_rows(lr)]
        label_rows = [r for lr in results for r in layer_to_label_rows(lr, labels)]
        trace_rows = [ev for lr in results for ev in lr.trace_samples]

        ctx.set_stage("building_plans")
        budgets = cfg.keep_budgets or DEFAULT_KEEP_BUDGETS
        saliency_json = [r.model_dump(mode="json") for r in sql_rows]
        plans = build_plans(
            num_layers=model.num_hidden_layers,
            num_experts=model.num_local_experts,
            source_model_id=cfg.model_asset_id or source_arch or "atlas",
            saliency_rows=saliency_json,
            keep_budgets=budgets,
            expert_params=model.expert_params_per_expert(),
        )
        primary_k = min(max(1, min(budgets)), model.num_local_experts)
        keep_maps = build_keep_maps(
            num_layers=model.num_hidden_layers,
            num_experts=model.num_local_experts,
            source_model_id=cfg.model_asset_id or source_arch or "atlas",
            saliency_rows=saliency_json,
            top_k=primary_k,
        )

        ctx.set_stage("writing_artifacts")
        store.write_source_model(run_id, model)
        from datetime import datetime

        now = datetime.now(UTC)
        evidence = [
            "run_manifest.json",
            "layer_saliency.json",
            "saliency_by_label.json",
            "plans.json",
            "keep_maps.json",
            "trace.jsonl",
        ]
        manifest = {
            "atlas_run_id": run_id,
            "schema_version": "atlas-bridge-v1",
            "status": "completed",
            "source_arch": source_arch,
            "source_checkpoint_id": cfg.model_asset_id,
            "calibration_suite_id": cfg.suite_ref,
            "n_tasks": _suite_n_tasks(cfg),
            "trace_depth": cfg.trace_depth.value,
            "evidence_level": EvidenceLevel.basic_saliency.value,
            "evidence_present": evidence,
            "topology": model.topology,
            "capability_labels": labels,
            "num_tokens": pool.num_tokens(),
            "created_at": (job.created_at.isoformat() if job.created_at else now.isoformat()),
            "started_at": job.started_at.isoformat() if job.started_at else now.isoformat(),
            "completed_at": now.isoformat(),
            "software_revision": None,
        }
        store.write_artifacts(
            run_id,
            manifest=manifest,
            saliency_rows=saliency_json,
            saliency_by_label=label_rows,
            plans=plans,
            keep_maps=[km.model_dump(mode="json") for km in keep_maps],
            trace_rows=trace_rows,
        )
        # Link outputs to the source model asset.
        _link_source(store, models_store, run_id, cfg.model_asset_id)

        ctx.set_result(
            JobResult(
                artifact_paths=[str(store.run_dir(run_id))],
                extra={"atlas_run_id": run_id, "n_plans": len(plans)},
            )
        )
        ctx.finish(JobState.completed)

    return executor


def _suite_n_tasks(cfg: AtlasBuildConfig) -> int:
    from pathlib import Path as _P

    ref = cfg.suite_ref
    candidates = [_P(ref)]
    if not ref.endswith((".yaml", ".yml")):
        candidates.append(_P("configs/suites") / f"{ref}.yaml")
        candidates.append(_P("configs/suites") / f"{ref}.yml")
    else:
        candidates.append(_P("configs/suites") / ref)
    for cand in candidates:
        if cand.is_file():
            return len(load_suite_yaml(cand).tasks)
    return 0


def _link_source(
    store: AtlasRunStore, models_store: ModelAssetStore, run_id: str, asset_id: str
) -> None:
    asset = models_store.get(asset_id)
    if asset is None:
        return
    asset.source_atlas_run_id = run_id
    asset.last_atlas_run_id = run_id
    if "atlas-traced" not in (asset.tags or []):
        asset.tags = [*(asset.tags or []), "atlas-traced"]
    models_store.save(asset)


def _read_json(path: Path) -> Any:
    import json

    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _file_len(path: Path) -> int:
    data = _read_json(path)
    return len(data) if isinstance(data, list) else 0


def _jsonl_len(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        return sum(1 for _ in path.open(encoding="utf-8"))
    except OSError:
        return 0


def _parse_ts(value: Any) -> datetime | None:
    from datetime import datetime

    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).astimezone(UTC)
    except ValueError:
        return None

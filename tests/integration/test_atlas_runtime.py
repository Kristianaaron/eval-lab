"""Integration tests: M3 Atlas Lab runtime (genuine lightweight MoE tracer)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

import eval_lab.services.atlas_runtime as ar_mod  # noqa: E402
from eval_lab.dashboard import create_app  # noqa: E402
from eval_lab.schemas.atlas_runtime import AtlasBuildConfig, TraceDepth  # noqa: E402
from eval_lab.schemas.model_asset import (  # noqa: E402
    ModelAssetRecord,
    ModelAssetType,
    ValidationState,
)
from eval_lab.services.atlas_bridge import AtlasBridgeService  # noqa: E402
from eval_lab.services.atlas_runtime import AtlasRuntimeService  # noqa: E402
from eval_lab.services.orchestrator import JobOrchestrator  # noqa: E402
from eval_lab.storage.model_assets import ModelAssetStore  # noqa: E402

CFG = dict(model_asset_id="mini-src", suite_ref="smoke_direct.yaml", trace_depth="smoke")


def _register_source(models: ModelAssetStore, asset_id: str = "mini-src") -> None:
    models.save(
        ModelAssetRecord(
            asset_id=asset_id,
            name="Mini source",
            asset_type=ModelAssetType.source_checkpoint,
            architecture="k3-mini",
            atlas_compatible=True,
            validation_state=ValidationState.valid,
        )
    )


def _models(tmp_path: Path) -> ModelAssetStore:
    m = ModelAssetStore(tmp_path / "models")
    _register_source(m)
    return m


def _service(tmp_path: Path) -> tuple[AtlasRuntimeService, ModelAssetStore, Path]:
    models = _models(tmp_path)
    orch = JobOrchestrator(tmp_path / "jobs")
    svc = AtlasRuntimeService(orch, tmp_path / "atlas_out", models_store=models)
    return svc, models, tmp_path / "atlas_out"


def _wait_terminal(svc: AtlasRuntimeService, job_id: str, timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = svc.get(job_id)
        if j and j.state.value in (
            "completed",
            "failed",
            "cancelled",
            "failed_recoverable",
            "completed_with_warnings",
        ):
            return j.model_dump(mode="json")
        time.sleep(0.05)
    raise AssertionError("atlas job did not reach a terminal state in time")


def test_estimate_and_complete_run_persists_real_artifacts(tmp_path: Path) -> None:
    svc, models, out_root = _service(tmp_path)
    cfg = AtlasBuildConfig(**CFG)
    est = svc.estimate(cfg)
    assert est.num_layers == 6
    assert est.num_experts == 8
    assert est.num_tokens > 0
    assert est.estimated_wall_s >= 0
    assert est.methodology  # honest labelling

    job = svc.launch(cfg)
    assert job.job_id.startswith("atlas-")
    final = _wait_terminal(svc, job.job_id)
    assert final["state"] == "completed"
    assert final["progress"]["done"] == 6  # one progress tick per traced layer

    run_id = job.config["atlas_run_id"]
    detail = svc.run_detail(run_id)
    assert detail is not None
    assert detail.status == "completed"
    assert detail.source_checkpoint_id == "mini-src"
    assert detail.calibration_suite_id == "smoke_direct.yaml"
    assert detail.n_tasks == 5  # smoke_direct suite
    assert len(detail.saliency) == 6 * 8  # one row per (layer, expert)
    assert detail.trace_count > 0
    # non-trivial routing: saliency values differ across experts
    sals = [s.total_value for s in detail.saliency]
    assert len(set(round(v, 4) for v in sals)) > 1
    # candidate plans span full + trim budgets
    names = [p.name for p in detail.plans]
    assert "keep8-full" in names
    assert any(n.endswith("-saliency") for n in names)

    # artifacts on disk conform to the bridge contract and import cleanly
    run_dir = out_root / "atlas_runs" / run_id
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    assert manifest["status"] == "completed"
    assert manifest["source_checkpoint_id"] == "mini-src"
    assert "source_model" in {p.name for p in run_dir.glob("*")}
    bridge = AtlasBridgeService(out_root, models_root=tmp_path / "models")
    rec = bridge.import_run(run_id)
    assert rec.status == "completed"
    assert rec.n_plans == len(detail.plans)
    # keep-map saliency is populated from real measurements
    km0 = rec.plans[0].keep_maps[0]
    assert any(e.saliency is not None for e in km0.entries)

    # outputs linked to source model
    assert models.get("mini-src").source_atlas_run_id == run_id
    assert "atlas-traced" in (models.get("mini-src").tags or [])


def test_pause_and_resume_resumes_from_checkpoint(monkeypatch, tmp_path: Path) -> None:
    real = ar_mod.trace_layer

    def slow(model, layer, pool, top_k=None):
        time.sleep(0.15)
        return real(model, layer, pool, top_k)

    monkeypatch.setattr(ar_mod, "trace_layer", slow)
    svc, models, _ = _service(tmp_path)
    job = svc.launch(AtlasBuildConfig(**CFG))
    time.sleep(0.5)
    svc.pause(job.job_id)
    for _ in range(200):
        j = svc.get(job.job_id)
        if j.state.value == "paused":
            break
        time.sleep(0.05)
    assert svc.get(job.job_id).state.value == "paused"
    checkpoint = svc.store.load_last_layer(job.config["atlas_run_id"])
    assert checkpoint is not None
    assert checkpoint < svc.get(job.job_id).progress.total - 1
    partials = svc.store.load_layer_partials(job.config["atlas_run_id"])
    assert {r.layer for r in partials} == set(range(checkpoint + 1))

    svc.resume(job.job_id)
    final = _wait_terminal(svc, job.job_id)
    assert final["state"] == "completed"
    detail = svc.run_detail(job.config["atlas_run_id"])
    assert len(detail.saliency) == 6 * 8  # resumed run still measures all layers


def test_restart_recovery_flags_and_resumes(monkeypatch, tmp_path: Path) -> None:
    real = ar_mod.trace_layer

    def slow(model, layer, pool, top_k=None):
        time.sleep(0.15)
        return real(model, layer, pool, top_k)

    monkeypatch.setattr(ar_mod, "trace_layer", slow)
    jobs_dir = tmp_path / "jobs"
    orch1 = JobOrchestrator(jobs_dir)
    svc1 = AtlasRuntimeService(orch1, tmp_path / "atlas_out", models_store=_models(tmp_path))
    job = svc1.launch(AtlasBuildConfig(**CFG))
    run_id = job.config["atlas_run_id"]
    time.sleep(0.4)
    svc1.pause(job.job_id)
    for _ in range(200):
        j = orch1.get(job.job_id)
        if j.state.value == "paused":
            break
        time.sleep(0.05)

    # simulate a hard crash: the process dies while the job is "running"
    p = jobs_dir / f"{job.job_id}.json"
    data = json.loads(p.read_text())
    data["state"] = "running"
    p.write_text(json.dumps(data))

    # "restart": a fresh orchestrator over the same dir flags it recoverable
    orch2 = JobOrchestrator(jobs_dir)
    svc2 = AtlasRuntimeService(orch2, tmp_path / "atlas_out", models_store=_models(tmp_path))
    j = orch2.get(job.job_id)
    assert j.state.value == "failed_recoverable"
    assert j.interrupted is True

    svc2.resume(job.job_id)
    final = _wait_terminal(svc2, job.job_id)
    assert final["state"] == "completed"
    detail = svc2.run_detail(run_id)
    assert detail is not None and detail.status == "completed"
    assert len(detail.saliency) == 48


def test_wizard_api_endpoints(tmp_path: Path) -> None:
    c = TestClient(
        create_app(
            tmp_path / "runs",
            models_root=tmp_path / "models",
            atlas_root=tmp_path / "atlas_out",
        )
    )
    _register_source(ModelAssetStore(tmp_path / "models"))

    cfg = c.get("/api/atlas/config").json()
    assert cfg["sources"]
    assert {d["depth"] for d in cfg["trace_depths"]} == {
        TraceDepth.smoke.value,
        TraceDepth.basic.value,
        TraceDepth.full.value,
    }
    assert cfg["suites"]

    est = c.post("/api/atlas/estimate", json=CFG).json()
    assert est["num_tokens"] > 0

    job = c.post("/api/atlas-jobs", json=CFG).json()
    assert job["job_id"].startswith("atlas-")
    for _ in range(300):
        j = c.get(f"/api/atlas-jobs/{job['job_id']}").json()
        if j["state"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    assert j["state"] == "completed"

    runs = c.get("/api/atlas-runs").json()
    assert runs and runs[0]["status"] == "completed"
    d = c.get(f"/api/atlas-runs/{runs[0]['atlas_run_id']}").json()
    assert d["status"] == "completed"
    assert d["plans"]

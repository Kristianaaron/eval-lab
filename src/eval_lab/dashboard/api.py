"""Read-only FastAPI server over eval-lab run data (spec repo: web dashboard).

The Python eval pipeline remains the producer; this API is a thin, typed,
read-only layer over the SQLite index plus the portable JSON/JSONL artifacts
in ``runs/<run-id>/``. It deliberately has no write access to runs.
"""

from __future__ import annotations

import json
import os
from datetime import UTC
from pathlib import Path
from typing import Any, cast

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from eval_lab.adapters.factory import build_adapter
from eval_lab.schemas.atlas_runtime import AtlasBuildConfig
from eval_lab.schemas.evaluation import EvaluationConfig
from eval_lab.schemas.experiment import ExperimentType
from eval_lab.schemas.model_asset import (
    EnvBudget,
    InspectPathRequest,
    RegisterEndpointRequest,
    RegisterRequest,
)
from eval_lab.schemas.models import ModelConfig, TaskSpec
from eval_lab.services.atlas_bridge import AtlasBridgeService
from eval_lab.services.atlas_runtime import AtlasRuntimeService
from eval_lab.services.comparisons import ComparisonService
from eval_lab.services.environment import environment_status
from eval_lab.services.evaluations import EvaluationService
from eval_lab.services.experiments import ExperimentService
from eval_lab.services.models import ModelAssetService, seed_fixtures
from eval_lab.services.orchestrator import JobOrchestrator
from eval_lab.storage.model_assets import ModelAssetStore
from eval_lab.storage.sqlite import RunStore
from eval_lab.tasks.loader import TaskLoadError, load_suite_yaml, load_task_yaml


class SuiteCreate(BaseModel):
    name: str
    domains: list[str]


class AtlasImportRequest(BaseModel):
    run_id: str


class ProfilerBenchmarkRequest(BaseModel):
    """Launch the standard benchmark for a profiler-produced model asset."""

    suite_ref: str = "configs/suites/daily_driver.yaml"
    repeat_count: int = 1


class ExperimentCreateRequest(BaseModel):
    run_id: str
    plan_name: str
    objective: str = ""
    memory_target_bytes: int | None = None
    experiment_type: ExperimentType = ExperimentType.keep_map


_SLUG_KEEP = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_-")


def _task_index(tasks_dir: str = "tasks") -> dict[str, TaskSpec]:
    index: dict[str, TaskSpec] = {}
    for p in Path(tasks_dir).rglob("*.yaml"):
        try:
            t = load_task_yaml(p)
        except TaskLoadError:
            continue
        index[t.id] = t
    return index


def _available_domains() -> list[str]:
    doms: set[str] = set()
    for t in _task_index().values():
        doms.update(t.labels.domains)
    # Presets are curated views over the task corpus, rather than synthetic
    # labels. This keeps every item selectable in the UI backed by a runnable
    # suite while giving users the vocabulary they use when benchmarking.
    doms.update(_DOMAIN_PRESETS)
    return sorted(doms)


# User-facing benchmark intents mapped to the controlled task domains. The
# mapping is deliberately kept in the API layer so adding a preset does not
# require relabelling dozens of task manifests or changing their semantics.
_DOMAIN_PRESETS: dict[str, set[str]] = {
    "software_engineering": {"coding", "frontend", "agentic", "tool_calling"},
    "instruction_following": {"coding", "frontend", "general_reasoning"},
    "code_generation": {"coding", "frontend"},
    "debugging": {"coding", "agentic"},
    "planning": {"agentic", "tool_calling"},
    "retrieval": {"long_context", "research"},
    "structured_output": {"coding", "tool_calling", "voxel"},
    "factuality": {"general_reasoning", "research", "long_context"},
}


def _slug(name: str) -> str:
    out = "".join(c if c in _SLUG_KEEP else "-" for c in name.lower()).strip("-")
    return out or "suite"


def build_suite_from_domains(
    name: str, domains: list[str], tasks_dir: str = "tasks"
) -> tuple[str, int]:
    """Write a suite YAML containing tasks whose labels overlap the domains.

    Returns (suite_ref, task_count). Domain list is a union filter, so adding
    domains later is just adding to the picker and this keeps scaling.
    """
    requested = set(domains)
    wanted = set().union(*(_DOMAIN_PRESETS.get(domain, {domain}) for domain in requested))
    tasks_by_id = _task_index(tasks_dir)
    selected = sorted(
        (t for t in tasks_by_id.values() if set(t.labels.domains) & wanted),
        key=lambda t: t.id,
    )
    slug = _slug(name)
    payload = {
        "schema_version": "1.0",
        "id": f"suite.user.{slug}.001",
        "name": name,
        "description": f"User suite from domains: {', '.join(sorted(wanted))}",
        "version": 1,
        "family": "user",
        "tasks": [{"task_id": t.id, "weight": 1.0} for t in selected],
    }
    out = Path("configs/suites") / f"{slug}.yaml"
    out.write_text(yaml.safe_dump(payload, sort_keys=False))
    return str(out), len(selected)


_RUN_FIELDS = (
    "run_id",
    "created_at",
    "task_id",
    "task_version",
    "model_id",
    "harness_id",
    "suite_id",
    "level",
    "status",
    "aggregate_score",
    "passed",
    "run_dir",
)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _load_events(trace_path: Path) -> list[dict[str, Any]]:
    """Parse trace.jsonl into a list of event dicts (with seq order preserved)."""
    if not trace_path.is_file():
        return []
    events: list[dict[str, Any]] = []
    try:
        for line in trace_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return events


def _flatten(d: dict[str, Any], prefix: str = "") -> list[tuple[str, float]]:
    """Flatten a telemetry payload into 'path -> scalar' series for charting."""
    out: list[tuple[str, float]] = []
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            out.append((key, float(v)))
        elif isinstance(v, dict):
            out.extend(_flatten(v, key))
    return out


class DashboardApp:
    """Factory that builds the FastAPI app bound to a runs root + sqlite index."""

    def __init__(
        self,
        runs_root: str | Path,
        db_path: str | Path | None = None,
        models_root: str | Path | None = None,
        atlas_root: str | Path | None = None,
    ) -> None:
        if FastAPI is None:
            raise RuntimeError("dashboard requires the 'serve' extra: uv pip install -e '.[serve]'")
        self.runs_root = Path(runs_root)
        self.db_path = Path(db_path) if db_path is not None else self.runs_root / "runstore.db"
        self.models_root = (
            Path(models_root) if models_root is not None else self.runs_root.parent / "models"
        )
        self.atlas_root = (
            Path(atlas_root) if atlas_root is not None else self.runs_root.parent / "atlas_out"
        )
        self.experiments_root = self.runs_root.parent / "experiments"
        self.app = FastAPI(title="eval-lab dashboard", version="1.0.0")
        self._store = RunStore(self.db_path)
        self._models = ModelAssetService(self.models_root)
        self._budget = EnvBudget()
        self._jobs = JobOrchestrator(self.runs_root.parent / "jobs")
        self._evaluations = EvaluationService(
            self.runs_root.parent / "jobs",
            runs_root=self.runs_root,
            db=self.db_path,
            tasks_dir="tasks",
            suites_dir="configs/suites",
            model_factory=self._build_evaluation_model,
            orchestrator=self._jobs,
        )
        self._comparisons = ComparisonService(
            runs_root=self.runs_root, db=self.db_path, tasks_dir="tasks"
        )
        self._atlas = AtlasBridgeService(self.atlas_root, models_root=self.models_root)
        self._atlas_runtime = AtlasRuntimeService(
            self._jobs,
            self.atlas_root,
            models_store=ModelAssetStore(self.models_root),
        )
        self._experiments = ExperimentService(
            self._atlas,
            self.experiments_root,
            models_store=ModelAssetStore(self.models_root),
        )
        self._register()
        self._register_models()
        self._register_platform()
        self._register_atlas()
        self._register_atlas_bridge()
        self._register_atlas_runtime()
        self._register_experiments()
        self._register_explorer()
        self._mount_spa()

    def _build_evaluation_model(self, job: Any) -> Any:
        """Resolve the selected registry asset to the adapter that will run it."""
        cfg = EvaluationConfig.model_validate(job.config)
        if cfg.model_id == "mock":
            return build_adapter(
                ModelConfig(id="mock", provider_type="mock", model_name="mock-deterministic")
            )
        asset = self._models.get_model_asset(cfg.model_asset_id)
        if asset is None:
            raise ValueError(f"model asset not found: {cfg.model_asset_id}")
        if asset.asset_id != cfg.model_id:
            raise ValueError(f"model_id {cfg.model_id!r} does not match asset {asset.asset_id!r}")
        if not asset.runnable:
            raise ValueError(f"model asset is not runnable: {asset.name}")
        if not asset.endpoint or not asset.model_name:
            raise ValueError(
                f"model asset {asset.name!r} has no endpoint/model name configured; "
                "register an OpenAI-compatible endpoint first"
            )
        api_key = os.getenv(asset.api_key_env) if asset.api_key_env else None
        return build_adapter(
            ModelConfig(
                id="selected-model",
                provider_type="openai_compatible",
                endpoint=asset.endpoint,
                model_name=asset.model_name,
                api_key=api_key,
            )
        )

    # -- route registration -------------------------------------------------
    def _register(self) -> None:
        app = self.app

        @app.get("/api/health")
        def health() -> dict[str, Any]:
            db_ok = self.db_path.is_file()
            return {
                "status": "ok" if db_ok else "degraded",
                "runs_root": str(self.runs_root),
                "db": str(self.db_path),
                "db_exists": db_ok,
            }

        @app.get("/api/overview")
        def overview() -> dict[str, Any]:
            runs = self._store.list_runs(limit=10_000)
            by_status: dict[str, int] = {}
            passed = 0
            scored: list[float] = []
            for r in runs:
                status = str(r.get("status", "unknown"))
                by_status[status] = by_status.get(status, 0) + 1
                if r.get("passed"):
                    passed += 1
                agg = r.get("aggregate_score")
                if agg is not None:
                    scored.append(float(cast(float, agg)))
            avg = round(sum(scored) / len(scored), 4) if scored else None
            models = sorted(
                {str(m) for m in (r.get("model_id") for r in runs) if r.get("model_id")}
            )
            tasks = sorted({str(t) for t in (r.get("task_id") for r in runs) if r.get("task_id")})
            suites = sorted(
                {str(s) for s in (r.get("suite_id") for r in runs) if r.get("suite_id")}
            )
            return {
                "total_runs": len(runs),
                "by_status": by_status,
                "passed": passed,
                "failed": len(runs) - passed,
                "avg_aggregate_score": avg,
                "scored_runs": len(scored),
                "models": models,
                "tasks": tasks,
                "suites": suites,
            }

        @app.get("/api/models")
        def list_models() -> list[dict[str, Any]]:
            """Active models (models with runs) plus run-time stats.

            Run time for each run is read from the run manifest's ``duration_s``
            (falling back to ``None`` when the manifest is absent or lacks it), so
            the selector can show both how often a model has been exercised and
            how long its runs take.
            """
            runs = self._store.list_runs(limit=10_000)
            per: dict[str, dict[str, Any]] = {}
            for r in runs:
                mid = str(r.get("model_id") or "")
                if not mid:
                    continue
                entry = per.setdefault(mid, {"model_id": mid, "run_count": 0, "durations_s": []})
                entry["run_count"] += 1
                if r.get("run_dir"):
                    run_dir = Path(str(r["run_dir"]))
                else:
                    run_dir = self.runs_root / str(r["run_id"])
                manifest = _read_json(run_dir / "manifest.json")
                duration = manifest.get("duration_s") if manifest else None
                if isinstance(duration, (int, float)):
                    entry["durations_s"].append(float(duration))

            out: list[dict[str, Any]] = []
            for mid in sorted(per):
                e = per[mid]
                ds = sorted(e["durations_s"])
                stats: dict[str, Any] = {"model_id": mid, "run_count": e["run_count"]}
                if ds:
                    n = len(ds)
                    mid_idx = (n - 1) // 2
                    median = ds[mid_idx] if n % 2 else (ds[mid_idx] + ds[mid_idx + 1]) / 2
                    stats.update(
                        {
                            "min_duration_s": round(ds[0], 4),
                            "max_duration_s": round(ds[-1], 4),
                            "median_duration_s": round(median, 4),
                            "mean_duration_s": round(sum(ds) / n, 4),
                            "latest_duration_s": round(ds[-1], 4),
                        }
                    )
                else:
                    stats.update(
                        {
                            "min_duration_s": None,
                            "max_duration_s": None,
                            "median_duration_s": None,
                            "mean_duration_s": None,
                            "latest_duration_s": None,
                        }
                    )
                out.append(stats)
            return out

        @app.get("/api/runs")
        def list_runs(
            model_id: str | None = None,
            task_id: str | None = None,
            suite_id: str | None = None,
            status: str | None = None,
            limit: int = Query(200, ge=1, le=10_000),
        ) -> list[dict[str, Any]]:
            runs = self._store.list_runs(limit=10_000)
            out: list[dict[str, Any]] = []
            for r in runs:
                if model_id and r.get("model_id") != model_id:
                    continue
                if task_id and r.get("task_id") != task_id:
                    continue
                if suite_id and r.get("suite_id") != suite_id:
                    continue
                if status and r.get("status") != status:
                    continue
                out.append({k: r.get(k) for k in _RUN_FIELDS})
            out.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
            return out[: int(limit)]

        @app.get("/api/runs/{run_id}")
        def run_detail(run_id: str) -> dict[str, Any]:
            row = self._store.get_run(run_id)
            if row is None:
                raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
            run_dir = Path(str(row["run_dir"])) if row.get("run_dir") else self.runs_root / run_id
            manifest = _read_json(run_dir / "manifest.json")
            result = _read_json(run_dir / "result.json")
            scores = self._store.run_scores(run_id)
            report_path = run_dir / "report.md"
            report = report_path.read_text(encoding="utf-8") if report_path.is_file() else None
            artifacts_dir = run_dir / "artifacts"
            artifacts: list[str] = []
            if artifacts_dir.is_dir():
                artifacts = sorted(p.name for p in artifacts_dir.iterdir() if p.is_file())
            return {
                "run": {k: row.get(k) for k in _RUN_FIELDS},
                "manifest": manifest,
                "result": result,
                "scores": scores,
                "report": report,
                "artifacts": artifacts,
            }

        @app.get("/api/runs/{run_id}/trace")
        def run_trace(
            run_id: str,
            event_type: str | None = None,
            limit: int = Query(10_000, ge=1, le=100_000),
        ) -> list[dict[str, Any]]:
            run_dir = self.runs_root / run_id
            events = _load_events(run_dir / "trace.jsonl")
            if event_type:
                events = [e for e in events if e.get("event_type") == event_type]
            return events[: int(limit)]

        @app.get("/api/runs/{run_id}/telemetry")
        def run_telemetry(run_id: str) -> dict[str, Any]:
            run_dir = self.runs_root / run_id
            events = _load_events(run_dir / "trace.jsonl")
            samples = [e for e in events if e.get("event_type") == "resource_sample"]
            series: dict[str, list[dict[str, Any]]] = {}
            nodes: set[str] = set()
            for s in samples:
                payload = s.get("payload", {})
                node = str(payload.get("node_id", "unknown"))
                nodes.add(node)
                for key, value in _flatten(payload):
                    series.setdefault(key, []).append(
                        {"t_ns": s.get("time_monotonic_ns"), "node": node, "value": value}
                    )
            return {
                "run_id": run_id,
                "nodes": sorted(nodes),
                "sample_count": len(samples),
                "series": series,
            }

    # Serve the built Svelte SPA last so API routes stay reachable.
    def _register_atlas_bridge(self) -> None:
        """Atlas-bridge routes: discover/import exported atlas runs (consumer)."""
        app = self.app
        atlas = self._atlas

        @app.get("/api/cebu-bridge/runs")
        def list_atlas_imports() -> list[dict[str, Any]]:
            return [
                {
                    "run_id": r.run_id,
                    "arch": r.arch,
                    "status": r.status,
                    "n_plans": r.n_plans,
                    "has_derivative": r.has_derivative,
                    "evidence_present": r.evidence_present,
                }
                for r in atlas.scan()
            ]

        @app.post("/api/cebu-bridge/import")
        def import_atlas_run(req: AtlasImportRequest) -> dict[str, Any]:
            try:
                rec = atlas.import_run(req.run_id)
            except FileNotFoundError:
                raise HTTPException(
                    status_code=404, detail=f"atlas run dir missing: {req.run_id}"
                ) from None
            return rec.model_dump(mode="json")

        @app.post("/api/cebu-bridge/runs/{run_id}/benchmark")
        def benchmark_profiler_output(run_id: str, req: ProfilerBenchmarkRequest) -> dict[str, Any]:
            """Import a Cebu Profiler export and launch Eval Lab in one action."""
            try:
                atlas.import_run(run_id)
            except FileNotFoundError:
                raise HTTPException(
                    status_code=404, detail=f"Cebu profile output missing: {run_id}"
                ) from None

            asset = next(
                (
                    a
                    for a in self._models.list_model_assets()
                    if a.source_atlas_run_id == run_id
                    and a.asset_type.value == "derivative_checkpoint"
                ),
                None,
            )
            if asset is None:
                raise HTTPException(
                    status_code=400, detail="profiler export has no quantized model asset"
                )
            if not asset.runnable:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"{asset.name} is registered, but has no runnable endpoint/model name. "
                        "Serve the quantized output with an OpenAI-compatible runtime and "
                        "re-export it "
                        "with endpoint and model_name metadata."
                    ),
                )
            try:
                cfg = EvaluationConfig(
                    model_asset_id=asset.asset_id,
                    model_id=asset.asset_id,
                    suite_ref=req.suite_ref,
                    repeat_count=req.repeat_count,
                    runs_root="runs",
                )
                job = self._evaluations.launch(cfg, name=f"benchmark {asset.name}")
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from None
            return {"asset": asset.model_dump(mode="json"), "job": job.model_dump(mode="json")}

        @app.get("/api/cebu-bridge/runs/{run_id}")
        def get_atlas_import(run_id: str) -> dict[str, Any]:
            rec = atlas.get_import(run_id)
            if rec is None:
                raise HTTPException(status_code=404, detail=f"atlas import not found: {run_id}")
            return rec.model_dump(mode="json")

    def _register_atlas_runtime(self) -> None:
        """M3 Atlas Lab runtime: build-atlas wizard + live layerwise trace job."""

        from eval_lab.config.labels import all_in
        from eval_lab.schemas.atlas_runtime import (
            DEFAULT_KEEP_BUDGETS,
            DEFAULT_MINI_MOE,
            TRACE_DEPTH_PARAMS,
            TraceDepth,
        )

        app = self.app
        runtime = self._atlas_runtime

        @app.get("/api/cebu/config")
        def atlas_config() -> dict[str, Any]:
            sources = [
                {
                    "asset_id": a.asset_id,
                    "name": a.name,
                    "arch": a.architecture,
                    "atlas_compatible": a.atlas_compatible,
                    "asset_type": a.asset_type,
                }
                for a in self._models.list_model_assets()
            ]
            suites: list[dict[str, Any]] = []
            suites_dir = Path("configs/suites")
            for p in sorted(suites_dir.glob("*.yaml")):
                try:
                    s = load_suite_yaml(p)
                except Exception:
                    continue
                suites.append(
                    {
                        "suite_ref": str(p),
                        "id": s.id,
                        "name": s.name,
                        "family": s.family,
                        "task_count": len(s.tasks),
                    }
                )
            return {
                "sources": sources,
                "suites": suites,
                "trace_depths": [
                    {
                        "depth": d.value,
                        "num_samples": TRACE_DEPTH_PARAMS[d][0],
                        "seq_len": TRACE_DEPTH_PARAMS[d][1],
                    }
                    for d in TraceDepth
                ],
                "capability_labels": [c for c in all_in("capability")][:12],
                "default_topology": DEFAULT_MINI_MOE,
                "default_keep_budgets": DEFAULT_KEEP_BUDGETS,
            }

        @app.post("/api/cebu/estimate")
        def atlas_estimate(cfg: AtlasBuildConfig) -> dict[str, Any]:
            return runtime.estimate(cfg).model_dump(mode="json")

        @app.post("/api/cebu-jobs")
        def create_atlas_job(cfg: AtlasBuildConfig) -> dict[str, Any]:
            job = runtime.launch(cfg)
            return job.model_dump(mode="json")

        @app.get("/api/cebu-jobs")
        def list_atlas_jobs() -> list[dict[str, Any]]:
            return [j.model_dump(mode="json") for j in runtime.list_jobs()]

        @app.get("/api/cebu-jobs/{job_id}")
        def get_atlas_job(job_id: str) -> dict[str, Any]:
            job = runtime.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail=f"atlas job not found: {job_id}")
            return job.model_dump(mode="json")

        @app.post("/api/cebu-jobs/{job_id}/cancel")
        def cancel_atlas_job(job_id: str) -> dict[str, Any]:
            job = runtime.cancel(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail=f"atlas job not found: {job_id}")
            return job.model_dump(mode="json")

        @app.post("/api/cebu-jobs/{job_id}/pause")
        def pause_atlas_job(job_id: str) -> dict[str, Any]:
            job = runtime.pause(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail=f"atlas job not found: {job_id}")
            return job.model_dump(mode="json")

        @app.post("/api/cebu-jobs/{job_id}/resume")
        def resume_atlas_job(job_id: str) -> dict[str, Any]:
            job = runtime.resume(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail=f"atlas job not found: {job_id}")
            return job.model_dump(mode="json")

        @app.get("/api/cebu-runs")
        def list_atlas_runs() -> list[dict[str, Any]]:
            return runtime.list_runs()

        @app.get("/api/cebu-runs/{run_id}")
        def get_atlas_run(run_id: str) -> dict[str, Any]:
            detail = runtime.run_detail(run_id)
            if detail is None:
                raise HTTPException(status_code=404, detail=f"atlas run not found: {run_id}")
            return detail.model_dump(mode="json")

    def _register_experiments(self) -> None:
        """Experiment (M5) CRUD: pin an imported atlas run + candidate plan."""
        app = self.app
        experiments = self._experiments

        @app.get("/api/experiments")
        def list_experiments() -> list[dict[str, Any]]:
            return [r.model_dump(mode="json") for r in experiments.list()]

        @app.post("/api/experiments")
        def create_experiment(req: ExperimentCreateRequest) -> dict[str, Any]:
            try:
                rec = experiments.create_from_plan(
                    req.run_id,
                    req.plan_name,
                    objective=req.objective,
                    memory_target_bytes=req.memory_target_bytes,
                    experiment_type=req.experiment_type,
                )
            except FileNotFoundError:
                raise HTTPException(
                    status_code=404, detail=f"atlas import not found: {req.run_id}"
                ) from None
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from None
            return rec.model_dump(mode="json")

        @app.get("/api/experiments/{experiment_id}")
        def get_experiment(experiment_id: str) -> dict[str, Any]:
            rec = experiments.get(experiment_id)
            if rec is None:
                raise HTTPException(
                    status_code=404, detail=f"experiment not found: {experiment_id}"
                )
            return rec.model_dump(mode="json")

        @app.delete("/api/experiments/{experiment_id}")
        def delete_experiment(experiment_id: str) -> dict[str, bool]:
            return {"deleted": experiments.delete(experiment_id)}

    def _register_explorer(self) -> None:
        """M4 Explorer: one cross-registry browse over every recorded artifact."""
        from eval_lab.tasks.loader import load_suite_yaml

        app = self.app

        @app.get("/api/explorer/registries")
        def explorer_registries() -> dict[str, Any]:
            runs = self._store.list_runs(limit=10_000)
            by_status: dict[str, int] = {}
            passed = 0
            scored: list[float] = []
            for r in runs:
                status = str(r.get("status", "unknown"))
                by_status[status] = by_status.get(status, 0) + 1
                if r.get("passed"):
                    passed += 1
                agg = r.get("aggregate_score")
                if agg is not None:
                    scored.append(float(cast(float, agg)))
            avg = round(sum(scored) / len(scored), 4) if scored else None

            jobs = self._evaluations.orchestrator.list()
            jobs_by_kind: dict[str, int] = {}
            jobs_by_status: dict[str, int] = {}
            for j in jobs:
                jobs_by_kind[str(j.kind)] = jobs_by_kind.get(str(j.kind), 0) + 1
                jobs_by_status[str(j.state)] = jobs_by_status.get(str(j.state), 0) + 1

            atlas_runs = [
                {
                    "run_id": r.run_id,
                    "arch": r.arch,
                    "status": r.status,
                    "n_plans": r.n_plans,
                    "has_derivative": r.has_derivative,
                    "evidence_present": r.evidence_present,
                }
                for r in self._atlas.scan()
            ]
            experiments = [r.model_dump(mode="json") for r in self._experiments.list()]
            model_assets = [
                {
                    "asset_id": a.asset_id,
                    "name": a.name,
                    "asset_type": a.asset_type,
                    "runnable": a.runnable,
                    "atlas_compatible": a.atlas_compatible,
                }
                for a in self._models.list_model_assets()
            ]
            suites: list[dict[str, Any]] = []
            suites_dir = Path("configs/suites")
            for p in sorted(suites_dir.glob("*.yaml")):
                try:
                    s = load_suite_yaml(p)
                except Exception:
                    continue
                suites.append(
                    {
                        "ref": str(p),
                        "id": s.id,
                        "name": s.name,
                        "family": s.family,
                        "task_count": len(s.tasks),
                    }
                )
            return {
                "runs": {
                    "total": len(runs),
                    "by_status": by_status,
                    "passed": passed,
                    "failed": len(runs) - passed,
                    "avg_aggregate_score": avg,
                },
                "jobs": {"total": len(jobs), "by_kind": jobs_by_kind, "by_status": jobs_by_status},
                "atlas_runs": atlas_runs,
                "experiments": experiments,
                "model_assets": model_assets,
                "suites": suites,
            }

    # Serve the built Svelte SPA last so API routes stay reachable.
    def _register_atlas(self) -> None:
        """Register the Atlas plugin routes (open/exchange with the Atlas engine)."""
        try:
            from eval_lab.plugins.atlas import register_atlas_routes

            register_atlas_routes(self.app)
        except ImportError:  # pragma: no cover - eval-lab serves without the plugin
            pass

    # -- route registration -------------------------------------------------
    def _mount_spa(self) -> None:
        dist = self.runs_root.parent / "dashboard" / "web" / "dist"
        if not dist.is_dir():
            # Fall back to a repo-relative path when runs_root is custom.
            dist = Path(__file__).resolve().parents[3] / "dashboard" / "web" / "dist"
        if dist.is_dir():  # pragma: no cover - depends on frontend build presence
            self.app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")

    # -- model-asset routes (Milestone 1: registry + inspection + eligibility) ----
    def _register_models(self) -> None:
        app = self.app
        models = self._models

        @app.get("/api/models-assets")
        def list_model_assets() -> list[dict[str, Any]]:
            return [a.model_dump(mode="json") for a in models.list_model_assets()]

        @app.get("/api/models-assets/{asset_id}")
        def get_model_asset(asset_id: str) -> dict[str, Any]:
            asset = models.get_model_asset(asset_id)
            if asset is None:
                raise HTTPException(status_code=404, detail=f"model asset not found: {asset_id}")
            el = models.eligibility(asset, self._budget)
            return {"record": asset.model_dump(mode="json"), "actions": el.model_dump(mode="json")}

        @app.post("/api/models-assets/inspect")
        def inspect_path(req: InspectPathRequest) -> dict[str, Any]:
            from eval_lab.inspection.checkpoint import inspect_checkpoint

            inspection = inspect_checkpoint(req.path, memory_gb=req.memory_gb)
            return {
                "inspection": inspection.model_dump(mode="json"),
                "recommend_atlas": inspection.atlas_compatible,
            }

        @app.post("/api/models-assets")
        def register_asset(req: RegisterRequest) -> dict[str, Any]:
            record, inspection = models.register_local_checkpoint(
                req.path,
                name=req.name,
                asset_id=req.asset_id,
                memory_gb=req.memory_gb,
            )
            actions = models.eligibility(record, self._budget)
            return {
                "record": record.model_dump(mode="json"),
                "inspection": inspection.model_dump(mode="json"),
                "actions": actions.model_dump(mode="json"),
            }

        @app.post("/api/models-assets/endpoint")
        def register_endpoint(req: RegisterEndpointRequest) -> dict[str, Any]:
            if not req.endpoint.strip() or not req.model_name.strip():
                raise HTTPException(status_code=400, detail="endpoint and model_name are required")
            try:
                record = models.register_endpoint(
                    req.name.strip(),
                    req.endpoint.strip(),
                    req.model_name.strip(),
                    asset_id=req.asset_id,
                    api_key_env=req.api_key_env,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from None
            return {
                "record": record.model_dump(mode="json"),
                "actions": models.eligibility(record, self._budget).model_dump(mode="json"),
            }

        @app.get("/api/models-assets/{asset_id}/actions")
        def asset_actions(asset_id: str) -> dict[str, Any]:
            asset = models.get_model_asset(asset_id)
            if asset is None:
                raise HTTPException(status_code=404, detail=f"model asset not found: {asset_id}")
            return models.eligibility(asset, self._budget).model_dump(mode="json")

        @app.delete("/api/models-assets/{asset_id}")
        def delete_asset(asset_id: str) -> dict[str, Any]:
            if not models.delete_model_asset(asset_id):
                raise HTTPException(status_code=404, detail=f"model asset not found: {asset_id}")
            return {"deleted": asset_id}

        @app.post("/api/models-assets/fixtures")
        def reseed_fixtures() -> dict[str, Any]:
            records = seed_fixtures(self.models_root)
            return {"seeded": [r.asset_id for r in records]}

    # -- platform routes (corrections + Milestone 2) ---------------------------
    def _register_platform(self) -> None:
        from pathlib import Path

        from eval_lab.tasks.loader import load_suite_yaml

        app = self.app
        eval_svc = self._evaluations
        orchestrator = eval_svc.orchestrator

        @app.get("/api/environment")
        def get_environment() -> dict[str, Any]:
            env = environment_status()
            return {
                "software_version": env.software_version,
                "nodes": env.nodes,
                "unified_memory_gb": env.unified_memory_gb,
                "reserved_system_gb": env.reserved_system_gb,
                "nvme_available_bytes": env.nvme_available_bytes,
                "gpu_present": env.gpu_present,
            }

        # -- generic job endpoints (any kind) --------------------------------
        @app.get("/api/jobs")
        def list_jobs(kind: str | None = None) -> list[dict[str, Any]]:
            jobs = orchestrator.list(kind=kind)
            return [j.model_dump(mode="json") for j in jobs]

        @app.get("/api/jobs/{job_id}")
        def get_job(job_id: str) -> dict[str, Any]:
            job = orchestrator.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
            return job.model_dump(mode="json")

        @app.post("/api/jobs/{job_id}/cancel")
        def cancel_job(job_id: str) -> dict[str, Any]:
            job = orchestrator.cancel(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
            return job.model_dump(mode="json")

        # -- evaluation launch/monitor (Milestone 2) -------------------------
        @app.get("/api/eval-config")
        def eval_config() -> dict[str, Any]:
            runnable = [
                {"asset_id": a.asset_id, "name": a.name, "model_id": a.asset_id}
                for a in self._models.list_model_assets()
                if a.runnable
            ]
            models = [
                {
                    "asset_id": "mock-deterministic",
                    "name": "Mock (deterministic)",
                    "model_id": "mock",
                },
                *runnable,
            ]
            suites: list[dict[str, Any]] = []
            suites_dir = Path("configs/suites")
            for p in sorted(suites_dir.glob("*.yaml")):
                try:
                    s = load_suite_yaml(p)
                except Exception:
                    continue
                suites.append(
                    {
                        "suite_ref": str(p),
                        "id": s.id,
                        "name": s.name,
                        "family": s.family,
                        "task_count": len(s.tasks),
                    }
                )
            from eval_lab.services.scorecard import BENCHMARK_GROUPS, suite_task_ids

            benchmarks = [
                {
                    "key": key,
                    "name": meta["name"],
                    "description": meta["description"],
                    "suite_ref": meta["suite"],
                    "task_count": len(suite_task_ids(meta["suite"])),
                }
                for key, meta in BENCHMARK_GROUPS.items()
            ]
            return {
                "models": models,
                "suites": suites,
                "benchmarks": benchmarks,
                "domains": _available_domains(),
                "harnesses": [
                    {"harness_id": "auto", "name": "Per task (direct / agent / perplexity)"},
                    {"harness_id": "direct", "name": "Direct (model-level)"},
                    {"harness_id": "agent-react", "name": "Agent (react + tools)"},
                ],
            }

        @app.post("/api/suites")
        def create_suite(payload: SuiteCreate) -> dict[str, Any]:
            suite_ref, count = build_suite_from_domains(payload.name, payload.domains)
            return {
                "suite_ref": suite_ref,
                "name": payload.name,
                "task_count": count,
                "domains": sorted(payload.domains),
            }

        @app.post("/api/eval-jobs")
        def create_eval_job(cfg: EvaluationConfig) -> dict[str, Any]:
            if cfg.model_id != "mock":
                asset = self._models.get_model_asset(cfg.model_asset_id)
                if asset is None or asset.asset_id != cfg.model_id:
                    raise HTTPException(status_code=400, detail="select a registered model asset")
                if not asset.runnable:
                    raise HTTPException(
                        status_code=400, detail=f"model asset is not runnable: {asset.name}"
                    )
            job = eval_svc.launch(cfg, name=f"evaluate {cfg.model_id}")
            return job.model_dump(mode="json")

        @app.get("/api/eval-jobs")
        def list_eval_jobs() -> list[dict[str, Any]]:
            return [j.model_dump(mode="json") for j in eval_svc.list()]

        @app.get("/api/eval-jobs/{job_id}")
        def get_eval_job(job_id: str) -> dict[str, Any]:
            job = eval_svc.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail=f"eval job not found: {job_id}")
            return job.model_dump(mode="json")

        @app.get("/api/eval-jobs/{job_id}/tree")
        def eval_job_tree(job_id: str) -> dict[str, Any]:
            """The job's suite as a task tree with live per-task state.

            Tasks run in suite order, so while a job is active the first
            ``progress.done`` tasks are finished and ``progress.detail`` names
            the one being evaluated. Scores come from the run index: the
            latest run of each task for the job's model since the job started.
            """
            from datetime import datetime

            try:
                job = eval_svc.get(job_id)
            except ValueError:
                job = None
            if job is None:
                raise HTTPException(status_code=404, detail=f"eval job not found: {job_id}")
            cfg = job.config
            suite_ref = str(cfg.get("suite_ref", ""))
            model_id = str(cfg.get("model_id", ""))
            try:
                suite = load_suite_yaml(suite_ref)
            except Exception as exc:
                raise HTTPException(status_code=404, detail=f"suite not loadable: {exc}") from exc
            index = _task_index()

            def _ts(value: object) -> datetime | None:
                if not value:
                    return None
                try:
                    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                except ValueError:
                    return None
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

            since = job.started_at or job.created_at
            latest: dict[str, dict[str, Any]] = {}
            for r in self._store.list_runs(limit=100_000):  # newest first
                tid = str(r.get("task_id") or "")
                if r.get("model_id") != model_id or tid in latest:
                    continue
                created = _ts(r.get("created_at"))
                if since is not None and created is not None and created < since:
                    continue
                latest[tid] = r

            active = job.state.value in ("queued", "running", "pausing", "paused", "resuming")
            current = job.progress.detail if active else None
            tasks: list[dict[str, Any]] = []
            for ref in suite.tasks:
                spec = index.get(ref.task_id)
                run = latest.get(ref.task_id)
                if run is not None:
                    status = "done"
                elif current == ref.task_id:
                    status = "running"
                else:
                    status = "pending"
                score = run.get("aggregate_score") if run else None
                tasks.append(
                    {
                        "task_id": ref.task_id,
                        "name": spec.name if spec else ref.task_id,
                        "group": ref.task_id.split(".", 1)[0],
                        "runner": spec.execution.runner if spec else None,
                        "status": status,
                        "run_id": run.get("run_id") if run else None,
                        "score": float(score) if isinstance(score, (int, float)) else None,
                        "passed": bool(run.get("passed")) if run else None,
                    }
                )
            return {
                "job_id": job.job_id,
                "state": job.state.value,
                "active": active,
                "model_id": model_id,
                "suite_ref": suite_ref,
                "suite_id": suite.id,
                "suite_name": suite.name,
                "current_task": current,
                "done": job.progress.done,
                "total": job.progress.total,
                "created_at": job.created_at.isoformat(),
                "tasks": tasks,
            }

        @app.post("/api/eval-jobs/{job_id}/cancel")
        def cancel_eval_job(job_id: str) -> dict[str, Any]:
            job = eval_svc.cancel(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail=f"eval job not found: {job_id}")
            return job.model_dump(mode="json")

        # -- standalone benchmark scorecard + perplexity ---------------------
        @app.get("/api/benchmark/groups")
        def benchmark_groups() -> list[dict[str, Any]]:
            """The standard benchmark groups with their suite and task counts."""
            from eval_lab.services.scorecard import BENCHMARK_GROUPS, suite_task_ids

            out: list[dict[str, Any]] = []
            for key, meta in BENCHMARK_GROUPS.items():
                ids = suite_task_ids(meta["suite"])
                out.append(
                    {
                        "key": key,
                        "name": meta["name"],
                        "description": meta["description"],
                        "suite_ref": meta["suite"],
                        "task_count": len(ids),
                        "task_ids": ids,
                    }
                )
            return out

        @app.get("/api/benchmark/scorecard")
        def benchmark_scorecard(model_id: str) -> dict[str, Any]:
            from eval_lab.services.scorecard import build_scorecard

            return build_scorecard(self._store, model_id, runs_root=self.runs_root).to_dict()

        @app.get("/api/benchmark/models")
        def benchmark_models() -> list[dict[str, Any]]:
            """Every model with runs, with its overall scorecard numbers (leaderboard)."""
            from eval_lab.services.scorecard import build_scorecard

            models = sorted(
                {
                    str(r.get("model_id"))
                    for r in self._store.list_runs(limit=100_000)
                    if r.get("model_id")
                }
            )
            rows: list[dict[str, Any]] = []
            for mid in models:
                card = build_scorecard(self._store, mid, runs_root=self.runs_root)
                ppl = [p["perplexity"] for p in card.perplexity.values() if p.get("perplexity")]
                rows.append(
                    {
                        "model_id": mid,
                        "total_runs": card.total_runs,
                        "scored_tasks": card.scored_tasks,
                        "overall_score": card.overall_score,
                        "overall_pass_rate": card.overall_pass_rate,
                        "groups": {
                            k: {
                                "mean_score": g.mean_score,
                                "pass_rate": g.pass_rate,
                                "task_count": g.task_count,
                            }
                            for k, g in card.groups.items()
                        },
                        "mean_perplexity": round(sum(ppl) / len(ppl), 3) if ppl else None,
                    }
                )
            rows.sort(key=lambda r: (r["overall_score"] is None, -(r["overall_score"] or 0)))
            return rows

        @app.get("/api/perplexity")
        def perplexity_runs(
            model_id: str | None = None, limit: int = Query(200, ge=1, le=10_000)
        ) -> list[dict[str, Any]]:
            """Perplexity runs (latest first) with their metrics."""
            out: list[dict[str, Any]] = []
            for r in self._store.list_runs(limit=100_000):
                if model_id and r.get("model_id") != model_id:
                    continue
                run_dir = self.runs_root / str(r["run_id"])
                manifest = _read_json(run_dir / "manifest.json") or {}
                metrics = manifest.get("metrics")
                if not isinstance(metrics, dict) or "perplexity" not in metrics:
                    continue
                out.append(
                    {
                        "run_id": r["run_id"],
                        "model_id": r.get("model_id"),
                        "task_id": r.get("task_id"),
                        "status": r.get("status"),
                        "created_at": r.get("created_at"),
                        "score": r.get("aggregate_score"),
                        "passed": r.get("passed"),
                        **{
                            k: metrics.get(k)
                            for k in (
                                "perplexity",
                                "bits_per_byte",
                                "bits_per_token",
                                "tokens",
                                "bytes",
                                "windows",
                                "elapsed_s",
                            )
                        },
                    }
                )
                if len(out) >= limit:
                    break
            return out

        @app.get("/api/runs/{run_id}/perplexity")
        def run_perplexity(run_id: str) -> dict[str, Any]:
            """Full per-window perplexity metrics for one run."""
            metrics = _read_json(self.runs_root / run_id / "metrics.json")
            if metrics is None:
                raise HTTPException(
                    status_code=404, detail=f"no perplexity metrics for run {run_id}"
                )
            return metrics

        # -- comparisons (Phase 5 engine via typed service) ------------------
        @app.get("/api/comparisons/compare")
        def compare_models(base: str, candidate: str, threshold: float = 0.05) -> dict[str, Any]:
            result = self._comparisons.compare(base, candidate, regress_threshold=threshold)
            return {
                **result.__dict__,
                "regressions": [r.task_id for r in result.regressions],
                "improvements": [r.task_id for r in result.improvements],
            }

        @app.get("/api/comparisons/slices")
        def comparison_slices(model: str, axis: str = "domain") -> dict[str, Any]:
            slices = self._comparisons.label_slices(model, axis=axis)
            return {
                "axis": axis,
                "model": model,
                "slices": {
                    k: {
                        "label": s.label,
                        "task_count": s.task_count,
                        "weighted_score": s.weighted_score,
                        "unweighted_score": s.unweighted_score,
                    }
                    for k, s in slices.items()
                },
            }

        @app.get("/api/comparisons/pareto")
        def comparison_pareto() -> list[dict[str, Any]]:
            return [
                {"label": p.label, "quality": p.quality, "latency": p.latency, "memory": p.memory}
                for p in self._comparisons.pareto()
            ]


def create_app(
    runs_root: str | Path,
    db_path: str | Path | None = None,
    models_root: str | Path | None = None,
    atlas_root: str | Path | None = None,
) -> FastAPI:
    app = DashboardApp(runs_root, db_path, models_root, atlas_root)
    # Seed synthetic fixtures on first startup so the GUI reflects real assets;
    # idempotent and harmless (no full-model loads, Milestone 1).
    if not app._models.list_model_assets():
        seed_fixtures(app.models_root)
    return app.app

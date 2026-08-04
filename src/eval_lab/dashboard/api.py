"""Read-only FastAPI server over eval-lab run data (spec repo: web dashboard).

The Python eval pipeline remains the producer; this API is a thin, typed,
read-only layer over the SQLite index plus the portable JSON/JSONL artifacts
in ``runs/<run-id>/``. It deliberately has no write access to runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from eval_lab.schemas.evaluation import EvaluationConfig
from eval_lab.schemas.experiment import ExperimentType
from eval_lab.schemas.model_asset import (
    EnvBudget,
    InspectPathRequest,
    RegisterRequest,
)
from eval_lab.schemas.models import TaskSpec
from eval_lab.services.atlas_bridge import AtlasBridgeService
from eval_lab.services.comparisons import ComparisonService
from eval_lab.services.environment import environment_status
from eval_lab.services.evaluations import EvaluationService
from eval_lab.services.experiments import ExperimentService
from eval_lab.services.models import ModelAssetService, seed_fixtures
from eval_lab.storage.model_assets import ModelAssetStore
from eval_lab.storage.sqlite import RunStore
from eval_lab.tasks.loader import TaskLoadError, load_task_yaml


class SuiteCreate(BaseModel):
    name: str
    domains: list[str]


class AtlasImportRequest(BaseModel):
    run_id: str


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
    return sorted(doms)


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
    wanted = set(domains)
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
        self._evaluations = EvaluationService(
            self.runs_root.parent / "jobs",
            runs_root=self.runs_root,
            db=self.db_path,
            tasks_dir="tasks",
            suites_dir="configs/suites",
        )
        self._comparisons = ComparisonService(
            runs_root=self.runs_root, db=self.db_path, tasks_dir="tasks"
        )
        self._atlas = AtlasBridgeService(self.atlas_root, models_root=self.models_root)
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
        self._register_experiments()
        self._mount_spa()

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
            return {
                "run": {k: row.get(k) for k in _RUN_FIELDS},
                "manifest": manifest,
                "result": result,
                "scores": scores,
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

        @app.get("/api/atlas-bridge/runs")
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

        @app.post("/api/atlas-bridge/import")
        def import_atlas_run(req: AtlasImportRequest) -> dict[str, Any]:
            try:
                rec = atlas.import_run(req.run_id)
            except FileNotFoundError:
                raise HTTPException(
                    status_code=404, detail=f"atlas run dir missing: {req.run_id}"
                ) from None
            return rec.model_dump(mode="json")

        @app.get("/api/atlas-bridge/runs/{run_id}")
        def get_atlas_import(run_id: str) -> dict[str, Any]:
            rec = atlas.get_import(run_id)
            if rec is None:
                raise HTTPException(status_code=404, detail=f"atlas import not found: {run_id}")
            return rec.model_dump(mode="json")

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
            return {
                "models": models,
                "suites": suites,
                "domains": _available_domains(),
                "harnesses": [
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

        @app.post("/api/eval-jobs/{job_id}/cancel")
        def cancel_eval_job(job_id: str) -> dict[str, Any]:
            job = eval_svc.cancel(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail=f"eval job not found: {job_id}")
            return job.model_dump(mode="json")

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

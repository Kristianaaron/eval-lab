"""Read-only FastAPI server over eval-lab run data (spec repo: web dashboard).

The Python eval pipeline remains the producer; this API is a thin, typed,
read-only layer over the SQLite index plus the portable JSON/JSONL artifacts
in ``runs/<run-id>/``. It deliberately has no write access to runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from eval_lab.storage.sqlite import RunStore

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

    def __init__(self, runs_root: str | Path, db_path: str | Path | None = None) -> None:
        if FastAPI is None:
            raise RuntimeError("dashboard requires the 'serve' extra: uv pip install -e '.[serve]'")
        self.runs_root = Path(runs_root)
        self.db_path = Path(db_path) if db_path is not None else self.runs_root / "runstore.db"
        self.app = FastAPI(title="eval-lab dashboard", version="1.0.0")
        self._store = RunStore(self.db_path)
        self._register()

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

        # Optionally serve a built Svelte SPA if present.
        dist = self.runs_root.parent / "dashboard" / "web" / "dist"
        if not dist.is_dir():
            # Fall back to a repo-relative path when runs_root is custom.
            dist = Path(__file__).resolve().parents[3] / "dashboard" / "web" / "dist"
        if dist.is_dir():  # pragma: no cover - depends on frontend build presence
            app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")


def create_app(runs_root: str | Path, db_path: str | Path | None = None) -> FastAPI:
    return DashboardApp(runs_root, db_path).app

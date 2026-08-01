"""eval-lab command-line interface (Phase 0 commands: spec 19)."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from eval_lab.adapters.base import ModelAdapter
from eval_lab.adapters.factory import build_adapter
from eval_lab.adapters.mock import MockModelAdapter
from eval_lab.reports.markdown import write_run_report
from eval_lab.runners.batch import run_batch, run_suite
from eval_lab.runners.direct import DirectRunner, RunContext, RunResult
from eval_lab.schemas.models import ModelConfig, SuiteSpec, TaskSpec
from eval_lab.storage.sqlite import RunStore
from eval_lab.tasks.loader import (
    TaskLoadError,
    check_fixture_references,
    load_suite_yaml,
    load_task_yaml,
)

app = typer.Typer(
    name="eval-lab",
    help="Local model and agent evaluation harness.",
    no_args_is_help=True,
)


def _emit_json(payload: object) -> None:
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def _err(message: str) -> None:
    typer.echo(f"error: {message}", err=True)


@app.command("doctor")
def doctor(
    json_out: bool = typer.Option(False, "--json", help="machine-readable output"),
) -> None:
    """Check that the environment and core packages are healthy."""
    ok = True
    checks: list[dict[str, object]] = []
    # 1: package import.
    try:
        import eval_lab  # noqa: F401

        checks.append({"check": "import", "ok": True})
    except Exception as exc:  # pragma: no cover
        ok = False
        checks.append({"check": "import", "ok": False, "detail": str(exc)})
    # 2: deterministic mock adapter.
    try:
        adapter = MockModelAdapter()
        result = adapter.generate(adapter_health_prompt())
        stable = result.text == adapter.generate(adapter_health_prompt()).text
        checks.append(
            {
                "check": "mock_adapter",
                "ok": stable,
                "detail": result.text if stable else "non-deterministic output",
            }
        )
        ok = ok and stable
    except Exception as exc:  # pragma: no cover
        ok = False
        checks.append({"check": "mock_adapter", "ok": False, "detail": str(exc)})
    # 3: schema round-trip.
    try:
        TaskSpec.model_validate(sample_task_dict())
        checks.append({"check": "schema_roundtrip", "ok": True})
    except Exception as exc:  # pragma: no cover
        ok = False
        checks.append({"check": "schema_roundtrip", "ok": False, "detail": str(exc)})

    status = "ok" if ok else "failed"
    if json_out:
        _emit_json({"status": status, "checks": checks})
    else:
        for c in checks:
            mark = "ok" if c["ok"] else "FAIL"
            detail = c.get("detail", "")
            typer.echo(f"[{mark}] {c['check']} {detail}".rstrip())
    raise typer.Exit(code=0 if ok else 1)


@app.command("validate")
def validate(
    kind: str = typer.Argument(..., help="'task' or 'suite'"),
    path: str = typer.Argument(..., help="path to the YAML file"),
    json_out: bool = typer.Option(False, "--json", help="machine-readable output"),
) -> None:
    """Validate a task or suite YAML file."""
    if kind == "task":
        try:
            task = load_task_yaml(path)
        except TaskLoadError as exc:
            result = {"valid": False, "path": path, "error": str(exc)}
            _emit(valid=False, json_out=json_out, result=result)
            raise typer.Exit(code=1) from exc
        missing = check_fixture_references(task, Path(path).parent)
        if missing:
            result = {
                "valid": False,
                "path": path,
                "error": f"missing fixtures: {', '.join(missing)}",
            }
            _emit(valid=False, json_out=json_out, result=result)
            raise typer.Exit(code=1)
        result = {"valid": True, "path": path, "id": task.id}
        _emit(valid=True, json_out=json_out, result=result)
    elif kind == "suite":
        try:
            suite = load_suite_yaml(path)
        except TaskLoadError as exc:
            result = {"valid": False, "path": path, "error": str(exc)}
            _emit(valid=False, json_out=json_out, result=result)
            raise typer.Exit(code=1) from exc
        result = {"valid": True, "path": path, "id": suite.id}
        _emit(valid=True, json_out=json_out, result=result)
    else:
        _emit(valid=False, json_out=json_out, result={"error": f"unknown kind: {kind}"})
        raise typer.Exit(code=2)


@app.command("list")
def list_tasks(
    tasks_dir: str = typer.Option("tasks", "--dir", help="directory to scan"),
    json_out: bool = typer.Option(False, "--json", help="machine-readable output"),
) -> None:
    """List tasks found in the tasks directory tree."""
    base = Path(tasks_dir)
    if not base.is_dir():
        _emit(valid=False, json_out=json_out, result={"error": f"not a directory: {tasks_dir}"})
        raise typer.Exit(code=1)
    found: list[dict[str, object]] = []
    for p in sorted(base.rglob("*.yaml")):
        try:
            task = load_task_yaml(p)
        except TaskLoadError:
            continue
        found.append(
            {
                "id": task.id,
                "name": task.name,
                "level": task.level.value,
                "domains": task.labels.domains,
                "path": str(p),
            }
        )
    if json_out:
        _emit_json({"count": len(found), "tasks": found})
    else:
        typer.echo(f"found {len(found)} task(s):")
        for t in found:
            typer.echo(f"  {t['id']:<48} {t['name']}")
    raise typer.Exit(code=0)


@app.command("run")
def run_command(
    kind: str = typer.Argument(..., help="'task' or 'suite'"),
    target: str = typer.Argument(..., help="task id or suite path/id"),
    model: str = typer.Option(
        "mock", "--model", help="model id; 'mock' uses deterministic adapter"
    ),
    endpoint: str = typer.Option(None, "--endpoint", help="OpenAI-compatible base URL"),
    model_name: str = typer.Option(None, "--model-name", help="endpoint model name"),
    tasks_dir: str = typer.Option("tasks", "--tasks-dir"),
    runs_root: str = typer.Option("runs", "--runs-root"),
    db: str = typer.Option("runs/runstore.db", "--db"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Run a task or suite against a model and score it."""
    adapter = _build_model(model, endpoint, model_name)
    store = RunStore(db)
    runner = DirectRunner()
    try:
        if kind == "task":
            task = _resolve_task(kind, target, tasks_dir)
            context = RunContext(
                task=task, model=adapter, model_id=model, runs_root=runs_root, store=store
            )
            results = run_batch(runner, [task], lambda t: context)
        elif kind == "suite":
            suite = _resolve_suite(target, tasks_dir)
            tasks_by_id = _index_tasks(tasks_dir)
            results = run_suite(
                runner,
                suite,
                tasks_by_id,
                lambda t: RunContext(
                    task=t, model=adapter, model_id=model, runs_root=runs_root, store=store
                ),
            )
        else:
            _err(f"unknown kind: {kind}")
            raise typer.Exit(code=2)
    finally:
        store.close()

    for r in results:
        write_run_report(r.run_dir)
    if json_out:
        _emit_json([_result_summary(r) for r in results])
    else:
        for r in results:
            status = "pass" if r.aggregate and r.aggregate.passed else "fail"
            typer.echo(
                f"{r.run_id}  {r.manifest.get('task_id')}  {status}  "
                f"score={r.aggregate.total if r.aggregate else 0.0:.3f}  "
                f"{r.duration_s:.2f}s"
            )
    raise typer.Exit(code=0)


@app.command("perf")
def perf_command(
    target: str = typer.Option(
        "configs/suites/hardware_perf.yaml", "--suite", help="suite YAML path"
    ),
    tasks_dir: str = typer.Option("tasks", "--tasks-dir"),
    runs_root: str = typer.Option("runs", "--runs-root"),
    db: str = typer.Option("runs/runstore.db", "--db"),
    interval_s: float = typer.Option(
        0.05, "--interval", help="telemetry sample interval (seconds)"
    ),
    node_id: str = typer.Option(None, "--node", help="node id for correlation"),
    warm: bool = typer.Option(True, "--warm/--cold", help="mark the run warm or cold"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Run the hardware/performance suite under telemetry (Phase 3).

    Uses a deterministic streaming adapter that reports first-token delay and
    decode rate, so TTFT and decode throughput can be verified against raw
    token timestamps recorded in each run's trace.
    """
    from eval_lab.adapters.timing import TimedMockAdapter
    from eval_lab.runners.perf import PerfRunner

    adapter = TimedMockAdapter()
    store = RunStore(db)
    runner = PerfRunner(
        interval_s=interval_s,
        node_id=node_id,
        warm_state="warm" if warm else "cold",
        cold_start=not warm,
    )
    try:
        suite = _resolve_suite(target, tasks_dir)
        tasks_by_id = _index_tasks(tasks_dir)
        results = run_suite(
            runner,
            suite,
            tasks_by_id,
            lambda t: RunContext(
                task=t, model=adapter, model_id="mock-timed", runs_root=runs_root, store=store
            ),
        )
    finally:
        store.close()

    for r in results:
        write_run_report(r.run_dir)
    if json_out:
        _emit_json([_result_summary(r) for r in results])
    else:
        for r in results:
            m = r.manifest
            timing = m.get("timing")
            ttft = timing.get("ttft_s") if isinstance(timing, dict) else None
            decode_tps = timing.get("decode_tokens_per_s") if isinstance(timing, dict) else None
            status = "pass" if r.aggregate and r.aggregate.passed else "fail"
            typer.echo(
                f"{r.run_id}  {m.get('task_id')}  {status}  "
                f"ttft={ttft}s  decode_tps={decode_tps}  "
                f"{r.duration_s:.2f}s"
            )
    raise typer.Exit(code=0)


@app.command("serve")
def serve_command(
    runs_root: str = typer.Option("runs", "--runs-root"),
    db: str = typer.Option(None, "--db", help="sqlite index; default <runs-root>/runstore.db"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8100, "--port", min=1, max=65535),
    reload: bool = typer.Option(False, "--reload", help="dev: auto-reload on code change"),
) -> None:
    """Serve the read-only web dashboard over run data (FastAPI + Svelte SPA)."""
    try:
        import uvicorn

        from eval_lab.dashboard import create_app
    except ImportError as exc:  # pragma: no cover
        _err(f"serve requires the 'serve' extra: uv pip install -e '.[serve]' ({exc})")
        raise typer.Exit(code=1) from None

    app_obj = create_app(runs_root, db)
    typer.echo(f"dashboard listening on http://{host}:{port}  (runs root: {runs_root})")
    uvicorn.run(app_obj, host=host, port=port, reload=reload, log_level="info")


@app.command("score")
def score_command(
    run_id: str = typer.Argument(...),
    db: str = typer.Option("runs/runstore.db", "--db"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Show scores for a completed run."""
    store = RunStore(db)
    try:
        run = store.get_run(run_id)
        if not run:
            _err(f"run not found: {run_id}")
            raise typer.Exit(code=1)
        scores = store.run_scores(run_id)
    finally:
        store.close()
    if json_out:
        _emit_json({"run": run, "scores": scores})
    else:
        typer.echo(f"run {run_id} [{run['status']}] aggregate={run['aggregate_score']}")
        for s in scores:
            typer.echo(
                f"  {s['scorer_id']:<16} {'PASS' if s['passed'] else 'fail':<5} "
                f"score={s['score']:.3f}"
            )


@app.command("report")
def report_command(
    run_id: str = typer.Argument(...),
    runs_root: str = typer.Option("runs", "--runs-root"),
) -> None:
    """Render and print the Markdown report for a run."""
    out = write_run_report(Path(runs_root) / run_id)
    typer.echo(out.read_text(encoding="utf-8"))


@app.command("list-runs")
def list_runs_command(
    db: str = typer.Option("runs/runstore.db", "--db"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List stored runs."""
    store = RunStore(db)
    try:
        runs = store.list_runs()
    finally:
        store.close()
    if json_out:
        _emit_json({"runs": runs})
    else:
        for r in runs:
            typer.echo(
                f"{r['run_id']}  {r.get('task_id', '')}  {r['status']}  "
                f"score={r.get('aggregate_score')}  {r.get('created_at', '')}"
            )


@app.command("calibrate-judge")
def calibrate_judge(
    judge_id: str = typer.Argument(..., help="judge id (configs/judges/<id>.yaml)"),
    judges_dir: str = typer.Option("configs/judges", "--judges-dir"),
    gold_dir: str = typer.Option("gold/judge_calibration", "--gold-dir"),
    out_dir: str = typer.Option("reports", "--out-dir"),
    offline: bool = typer.Option(
        False, "--offline", help="use the deterministic offline mock judge (no endpoint)"
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Calibrate a judge against the human gold set and print a VERDICT."""
    from eval_lab.judges.adapter import build_judge
    from eval_lab.judges.calibration import (
        load_gold_set,
        load_judge_config,
        run_calibration,
        write_calibration_report,
    )

    cfg_path = Path(judges_dir) / f"{judge_id}.yaml"
    if not cfg_path.is_file():
        _err(f"judge config not found: {cfg_path}")
        raise typer.Exit(code=1)
    config = load_judge_config(cfg_path)
    judge = build_judge(config, offline=offline)
    gold = load_gold_set(gold_dir, dimension=config.dimension)
    report = run_calibration(judge, gold, thresholds=config.thresholds)
    out_path = write_calibration_report(report, out_dir)
    if json_out:
        _emit_json(report.to_dict())
    else:
        typer.echo(f"VERDICT: {report.verdict}")
        typer.echo(f"report: {out_path}")
    raise typer.Exit(code=0)


# -- resolution helpers -------------------------------------------------------


def _resolve_task(kind: str, target: str, tasks_dir: str) -> TaskSpec:
    if kind == "task":
        p = Path(target) if Path(target).exists() else _find_task_by_id(target, tasks_dir)
        if p is None:
            _err(f"task not found: {target}")
            raise typer.Exit(code=1)
        return load_task_yaml(p)
    raise typer.Exit(code=2)


def _resolve_suite(target: str, tasks_dir: str) -> SuiteSpec:
    p = Path(target) if Path(target).exists() else None
    if p is None:
        _err(f"suite not found (pass a file path): {target}")
        raise typer.Exit(code=1)
    return load_suite_yaml(p)


def _find_task_by_id(task_id: str, tasks_dir: str) -> Path | None:
    base = Path(tasks_dir)
    for p in base.rglob("*.yaml"):
        try:
            if load_task_yaml(p).id == task_id:
                return p
        except TaskLoadError:
            continue
    return None


def _index_tasks(tasks_dir: str) -> dict[str, TaskSpec]:
    index: dict[str, TaskSpec] = {}
    for p in Path(tasks_dir).rglob("*.yaml"):
        try:
            t = load_task_yaml(p)
            index[t.id] = t
        except TaskLoadError:
            continue
    return index


def _build_model(model_id: str, endpoint: str | None, model_name: str | None) -> ModelAdapter:
    if model_id == "mock" or (not endpoint and model_id != "mock"):
        return build_adapter(
            ModelConfig(id="mock", provider_type="mock", model_name="mock-deterministic")
        )
    return build_adapter(
        ModelConfig(
            id=model_id,
            provider_type="openai_compatible",
            endpoint=endpoint,
            model_name=model_name or model_id,
        )
    )


def _result_summary(r: RunResult) -> dict[str, object]:
    d: dict[str, object] = dict(r.manifest)
    d["status"] = r.status
    d["aggregate"] = r.aggregate.total if r.aggregate else None
    return d


# -- sampling helpers ---------------------------------------------------------


def adapter_health_prompt() -> str:
    return "eval-lab health check"


def sample_task_dict() -> dict[str, object]:
    """A minimal-but-valid task used by the doctor command."""
    return {
        "schema_version": "1.0",
        "id": "smoke.hello_world",
        "name": "Hello world",
        "description": "A trivial deterministic task.",
        "input": {"instruction_file": "prompt.md"},
        "execution": {"runner": "direct"},
    }


def _emit(valid: bool, json_out: bool, result: dict[str, object]) -> None:
    if json_out:
        _emit_json(result)
    else:
        status = "valid" if valid else "invalid"
        typer.echo(f"{status}: {result.get('path', result.get('error', ''))}")


if __name__ == "__main__":  # pragma: no cover
    app()

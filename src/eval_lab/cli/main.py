"""eval-lab command-line interface (Phase 0 commands: spec 19)."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from eval_lab.adapters.base import ModelAdapter
from eval_lab.adapters.factory import build_adapter
from eval_lab.adapters.mock import MockModelAdapter
from eval_lab.analysis.rows import RunRow
from eval_lab.reports.markdown import write_run_report
from eval_lab.runners.batch import run_batch, run_suite
from eval_lab.runners.direct import DirectRunner, RunContext, RunResult
from eval_lab.schemas.models import ModelConfig, SuiteSpec, TaskLabels, TaskSpec
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


@app.command("evaluate")
def evaluate_command(
    suite_ref: str = typer.Argument(..., help="suite YAML path or id"),
    model_id: str = typer.Option(..., "--model", help="model id whose runs to aggregate"),
    tasks_dir: str = typer.Option("tasks", "--tasks-dir"),
    runs_root: str = typer.Option("runs", "--runs-root"),
    db: str = typer.Option("runs/runstore.db", "--db"),
    scenario: str = typer.Option(
        None, "--scenario", help="alternative weighting scenario (configs/reports/*.yaml)"
    ),
    out_dir: str = typer.Option("reports", "--out-dir"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Aggregate a weighted suite for one model and render a label-sliced report.

    The composite is recomputed from the suite config (per-task weights) and,
    when ``--scenario`` is given, an alternative weighting scenario. Raw
    unweighted aggregates are always shown next to the weighted ones.
    """
    from eval_lab.analysis import aggregate_task_rows, build_task_rows, load_run_rows
    from eval_lab.analysis.weighting import load_weighting_scenario, reweight_tasks
    from eval_lab.reports.analysis import render_suite_report, write_report

    suite = _resolve_suite(suite_ref, tasks_dir)
    tasks_index = _index_tasks(tasks_dir)

    def resolver(task_id: str) -> TaskLabels | None:
        spec = tasks_index.get(task_id)
        return spec.labels if spec else None

    store = RunStore(db)
    try:
        rows = load_run_rows(store, model_id=model_id, label_resolver=resolver, runs_root=runs_root)
    finally:
        store.close()

    weight_by_task = {ref.task_id: ref.weight for ref in suite.tasks}
    suite_rows = [r for r in rows if r.task_id in weight_by_task]
    task_rows = build_task_rows(suite_rows, weight_by_task)
    if scenario:
        task_rows = reweight_tasks(task_rows, load_weighting_scenario(scenario))
    agg = aggregate_task_rows(task_rows)

    markdown = render_suite_report(suite.id, agg, model_id=model_id)
    out_path = write_report(Path(out_dir) / f"suite_{suite.id}_{model_id}.md", markdown)
    if json_out:
        _emit_json(
            {
                "suite_id": suite.id,
                "model_id": model_id,
                "weighted_score": agg.weighted_score,
                "unweighted_score": agg.unweighted_score,
                "weighted_pass_rate": agg.weighted_pass_rate,
                "unweighted_pass_rate": agg.unweighted_pass_rate,
                "task_count": agg.task_count,
                "scored_tasks": agg.scored_tasks,
                "domains": {k: s.weighted_score for k, s in agg.slice("domain").items()},
                "report": str(out_path),
            }
        )
    else:
        typer.echo(markdown)
        typer.echo(f"\nwrote suite report: {out_path}")
    raise typer.Exit(code=0)


@app.command("compare")
def compare_command(
    a: str = typer.Argument(..., help="base: model id or run id"),
    b: str = typer.Argument(..., help="candidate: model id or run id"),
    tasks_dir: str = typer.Option("tasks", "--tasks-dir"),
    runs_root: str = typer.Option("runs", "--runs-root"),
    db: str = typer.Option("runs/runstore.db", "--db"),
    threshold: float = typer.Option(0.05, "--threshold", help="regression threshold"),
    out_dir: str = typer.Option("reports", "--out-dir"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Pair two model configurations (or two runs) on identical tasks and report.

    ``a``/``b`` are model ids (all matching runs) unless they name a single
    stored run id. Deltas are candidate-minus-base for the base/candidate pair.
    """
    from eval_lab.analysis import compare_groups
    from eval_lab.reports.analysis import render_comparison_report, write_report

    store = RunStore(db)
    try:
        run_ids = {str(r["run_id"]) for r in store.list_runs()}
        # Resolve args to a single run id or a model id filter.
        a_rows = (
            _select_rows(store, runs_root, run_id=a)
            if a in run_ids
            else _select_rows(store, runs_root, model_id=a)
        )
        b_rows = (
            _select_rows(store, runs_root, run_id=b)
            if b in run_ids
            else _select_rows(store, runs_root, model_id=b)
        )
    finally:
        store.close()

    result = compare_groups(
        a_rows, b_rows, base_label=a, candidate_label=b, regress_threshold=threshold
    )
    markdown = render_comparison_report(result)
    out_path = write_report(Path(out_dir) / f"compare_{a}_vs_{b}.md", markdown)
    if json_out:
        _emit_json(
            {
                "base": a,
                "candidate": b,
                "sample_size": result.sample_size,
                "mean_delta": result.mean_delta,
                "median_delta": result.median_delta,
                "ci": result.ci,
                "wins": result.wins,
                "ties": result.ties,
                "losses": result.losses,
                "regressions": [r.task_id for r in result.regressions],
                "improvements": [r.task_id for r in result.improvements],
                "significant": result.significant,
                "report": str(out_path),
            }
        )
    else:
        typer.echo(markdown)
        typer.echo(f"\nwrote comparison report: {out_path}")
    raise typer.Exit(code=0)


@app.command("pareto")
def pareto_command(
    tasks_dir: str = typer.Option("tasks", "--tasks-dir"),
    runs_root: str = typer.Option("runs", "--runs-root"),
    db: str = typer.Option("runs/runstore.db", "--db"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Compute the quality-vs-latency Pareto frontier across model configs.

    One point per model: quality = mean aggregate score, latency = mean run
    duration. Points with no duration data are dropped.
    """
    from eval_lab.analysis import Point, load_run_rows, pareto_frontier

    store = RunStore(db)
    try:
        rows = load_run_rows(store, runs_root=runs_root)
    finally:
        store.close()

    by_model: dict[str, list[float]] = {}
    latency: dict[str, list[float]] = {}
    for r in rows:
        if r.score is not None and r.duration_s is not None:
            by_model.setdefault(r.model_id, []).append(r.score)
            latency.setdefault(r.model_id, []).append(r.duration_s)
    points = [
        Point(
            label=m,
            quality=sum(v) / len(v),
            latency=sum(latency[m]) / len(latency[m]),
        )
        for m, v in by_model.items()
        if latency.get(m)
    ]
    frontier = pareto_frontier(points)
    if json_out:
        _emit_json(
            {
                "all": [
                    {"label": p.label, "quality": p.quality, "latency": p.latency} for p in points
                ],
                "frontier": [p.label for p in frontier],
            }
        )
    else:
        typer.echo("Pareto frontier (quality vs latency):")
        for p in frontier:
            typer.echo(f"  {p.label:<16} quality={p.quality:.4f}  latency={p.latency:.3f}s")
        if not frontier:
            typer.echo("  (no comparable points with both score and duration)")
    raise typer.Exit(code=0)


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


@app.command("atlas")
def atlas_command(
    json_out: bool = typer.Option(False, "--json", help="machine-readable JSON"),
) -> None:
    """Open/exchange with the Atlas engine (model-atlas) from the eval harness."""
    from eval_lab.plugins.atlas import check_atlas

    status = check_atlas()
    if json_out:
        _emit_json(status)
    else:
        typer.echo(f"atlas dashboard: {status['url']}")
        reachable = status.get("reachable")
        if reachable:
            typer.echo("reachable: yes")
            typer.echo("open in a browser: " + status["url"])
        else:
            typer.echo(f"reachable: no ({status.get('error')})")
    if not status.get("reachable"):
        raise typer.Exit(1)


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


def _select_rows(
    store: RunStore,
    runs_root: str,
    *,
    run_id: str | None = None,
    model_id: str | None = None,
) -> list[RunRow]:
    """Load analysis rows for one run id, one model, or all runs."""
    from eval_lab.analysis import load_run_rows

    rows = load_run_rows(store, runs_root=runs_root)
    if run_id is not None:
        return [r for r in rows if r.run_id == run_id]
    if model_id is not None:
        return [r for r in rows if r.model_id == model_id]
    return rows


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

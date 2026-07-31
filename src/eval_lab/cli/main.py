"""eval-lab command-line interface (Phase 0 commands: spec 19)."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from eval_lab.adapters.mock import MockModelAdapter
from eval_lab.schemas.models import TaskSpec
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


def _emit_json(payload: dict[str, object]) -> None:
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

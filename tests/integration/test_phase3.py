"""Phase 3 tests: telemetry sampling, perf timing, cold/warm markers."""

from __future__ import annotations

from pathlib import Path

from eval_lab.adapters.mock import MockModelAdapter
from eval_lab.adapters.timing import TimedMockAdapter
from eval_lab.runners.direct import DirectRunner, RunContext
from eval_lab.runners.perf import PerfRunner
from eval_lab.tasks.loader import load_task_yaml
from eval_lab.telemetry import collectors
from eval_lab.telemetry.correlation import parse_events

TASKS = Path(__file__).parent.parent.parent / "tasks"


def _perf_task():
    return load_task_yaml(TASKS / "hardware" / "perf_probe" / "task.yaml")


def _ctx(task, adapter, runs_root, **extra):
    return RunContext(
        task=task,
        model=adapter,
        model_id=adapter.metadata().model_name,
        runs_root=str(runs_root),
        extra=extra,
    )


def test_perf_runner_records_and_verifies_timing(tmp_path):
    adapter = TimedMockAdapter(first_token_delay_s=0.02, tokens_per_s=50)
    runner = PerfRunner(interval_s=0.02, node_id="node-A", warm_state="warm")
    task = _perf_task()
    result = runner.execute_task(task, _ctx(task, adapter, tmp_path))
    assert result.status == "completed"
    assert result.aggregate.passed

    events = parse_events(Path(result.run_dir) / "trace.jsonl")
    types = {e["event_type"] for e in events}
    assert {
        "model_request",
        "token_event",
        "model_completion",
        "resource_sample",
        "telemetry_marker",
        "telemetry_correlation",
    } <= types

    seqs = [e["sequence"] for e in events]
    assert seqs == sorted(seqs)
    assert all(isinstance(s, int) for s in seqs)

    m = result.manifest
    assert m["timing"]["ttft_agrees"] is True
    assert m["timing"]["decode_tps_agrees"] is True
    assert m["warm_state"] == "warm"
    assert Path(m["telemetry_stream"]) == Path(result.run_dir) / "trace.jsonl"
    assert m["telemetry"]["per_node"]["node-A"]["sample_count"] >= 1


def test_perf_runner_missing_metrics_do_not_corrupt_run(tmp_path, monkeypatch):
    monkeypatch.setattr(collectors, "collect_nvidia", lambda: [collectors._null("no gpu")])
    monkeypatch.setattr(
        collectors, "collect_system", lambda: {"available": False, "reason": "missing"}
    )
    adapter = TimedMockAdapter()
    runner = PerfRunner(interval_s=0.02)
    task = _perf_task()
    result = runner.execute_task(task, _ctx(task, adapter, tmp_path))
    assert result.status == "completed"
    assert result.aggregate.passed
    events = parse_events(Path(result.run_dir) / "trace.jsonl")
    assert any(e["event_type"] == "resource_sample" for e in events)
    assert result.manifest["timing"]["ttft_agrees"] is True


def test_perf_runner_cold_marker(tmp_path):
    adapter = TimedMockAdapter()
    runner = PerfRunner(interval_s=0.02, warm_state="cold", cold_start=True)
    task = _perf_task()
    result = runner.execute_task(task, _ctx(task, adapter, tmp_path))
    assert result.manifest["warm_state"] == "cold"
    events = parse_events(Path(result.run_dir) / "trace.jsonl")
    marker = next(e for e in events if e["event_type"] == "telemetry_marker")
    assert marker["payload"]["cold_start"] is True


def test_direct_runner_records_warm_marker(tmp_path):
    task = _perf_task()
    adapter = MockModelAdapter()
    result = DirectRunner().execute_task(task, _ctx(task, adapter, tmp_path))
    assert result.status == "completed"
    assert result.manifest["warm_state"] == "model"
    events = parse_events(Path(result.run_dir) / "trace.jsonl")
    marker = next(e for e in events if e["event_type"] == "telemetry_marker")
    assert marker["payload"]["warm_state"] == "model"

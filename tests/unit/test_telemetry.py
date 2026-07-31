"""Unit tests for telemetry collectors, sampler, timing adapter, correlation."""

from __future__ import annotations

import os
import time

from eval_lab.adapters.base import GenerationRequest
from eval_lab.adapters.timing import TimedMockAdapter
from eval_lab.telemetry import collectors
from eval_lab.telemetry.correlation import correlate, parse_events, verify_timing
from eval_lab.telemetry.sampler import TelemetrySampler, attach_to_recorder
from eval_lab.traces.recorder import TraceRecorder

# -- collectors ---------------------------------------------------------------


def test_collect_system_available_on_linux():
    metric = collectors.collect_system()
    assert metric["available"] is True
    assert metric["cpu_count"] >= 1
    assert isinstance(metric["mem_total_bytes"], int)


def test_collect_system_missing_meminfo_reports_unavailable(monkeypatch):
    def boom(*_args, **_kwargs):
        raise FileNotFoundError("no meminfo")

    monkeypatch.setattr(collectors, "open", boom, raising=False)
    metric = collectors.collect_system()
    assert metric["available"] is False


def test_collect_process_own_pid_available():
    metric = collectors.collect_process()
    assert metric["available"] is True
    assert metric["pid"] == os.getpid()


def test_collect_nvidia_missing_smi(monkeypatch):
    monkeypatch.setattr(collectors.shutil, "which", lambda _name: None)
    result = collectors.collect_nvidia()
    assert result == [collectors._null("nvidia-smi not installed")]


def test_collect_nvme_no_block_devices(monkeypatch):
    monkeypatch.setattr(collectors.os.path, "isdir", lambda _path: False)
    result = collectors.collect_nvme()
    assert result[0]["available"] is False


def test_collect_network_returns_interfaces():
    result = collectors.collect_network()
    assert isinstance(result, list)
    if result and result[0].get("available"):
        assert "rx_bytes" in result[0]


# -- sampler ------------------------------------------------------------------


def test_sampler_sample_contains_all_metric_groups():
    sampler = TelemetrySampler(node_id="n1")
    payload = sampler.sample()
    assert payload["node_id"] == "n1"
    assert payload["time_monotonic_ns"] > 0
    for key in ("system", "process", "nvme", "network", "nvidia"):
        assert key in payload


def test_sampler_summary_aggregates():
    sampler = TelemetrySampler(node_id="n1")
    sampler.samples = [sampler.sample(), sampler.sample()]
    summary = sampler.summary()
    assert summary["node_id"] == "n1"
    assert summary["sample_count"] == 2


def test_attach_to_recorder_writes_sequenced_events(tmp_path):
    recorder = TraceRecorder("r1", tmp_path / "trace.jsonl")
    sampler = TelemetrySampler(node_id="n1")
    sampler.start = lambda: None  # keep the test deterministic; no sampler thread
    attach_to_recorder(sampler, recorder)
    sampler.emit(sampler.label, sampler.sample())
    sampler.emit(sampler.label, sampler.sample())
    recorder.close()

    events = parse_events(tmp_path / "trace.jsonl")
    assert [e["event_type"] for e in events] == ["resource_sample", "resource_sample"]
    assert [e["sequence"] for e in events] == [0, 1]
    assert events[0]["run_id"] == "r1"


def test_sampler_thread_samples_over_time():
    collected = []
    sampler = TelemetrySampler(interval_s=0.02, emit=lambda _t, p: collected.append(p))
    sampler.start()
    time.sleep(0.07)
    sampler.stop()
    assert len(collected) >= 1
    assert len(sampler.samples) == len(collected)


# -- timing adapter -----------------------------------------------------------


def test_timed_mock_streams_with_raw_timestamps():
    adapter = TimedMockAdapter(first_token_delay_s=0.01, tokens_per_s=100)
    stamps = []
    result = adapter.generate_stream(
        GenerationRequest(prompt="hi"), lambda _tok, s: stamps.append(s)
    )
    assert result.timing is not None
    assert result.timing.ttft_s is not None and result.timing.ttft_s > 0
    assert len(stamps) == len(result.text.split())


# -- correlation + timing verification ---------------------------------------


def test_verify_timing_recomputes_from_raw_events(tmp_path):
    recorder = TraceRecorder("r1", tmp_path / "trace.jsonl")
    adapter = TimedMockAdapter(first_token_delay_s=0.02, tokens_per_s=50)
    recorder.record("model_request", {})
    adapter.generate_stream(
        GenerationRequest(prompt="x"),
        lambda t, s: recorder.record(
            "token_event", {"wall_time_ns": int(s * 1e9), "token_len": len(t)}
        ),
    )
    recorder.record(
        "model_completion",
        {
            "ttft_s": 0.02,
            "decode_duration_s": 0.02,
            "decode_tokens_per_s": 50,
            "completion_tokens": 2,
        },
    )
    recorder.close()

    vt = verify_timing(parse_events(tmp_path / "trace.jsonl"))
    assert vt["available"] is True
    assert vt["token_count"] == 2
    assert vt["ttft_agrees"] is True
    assert vt["decode_tps_agrees"] is True


def test_correlate_groups_by_node():
    events = [
        {
            "event_type": "resource_sample",
            "payload": {
                "node_id": "a",
                "nvidia": [{"utilization_gpu": 10}],
                "system": {"mem_available_bytes": 100},
            },
        },
        {
            "event_type": "resource_sample",
            "payload": {
                "node_id": "a",
                "nvidia": [{"utilization_gpu": 90}],
                "system": {"mem_available_bytes": 50},
            },
        },
        {
            "event_type": "resource_sample",
            "payload": {
                "node_id": "b",
                "nvidia": [{"utilization_gpu": 40}],
                "system": {"mem_available_bytes": 200},
            },
        },
        {"event_type": "other", "payload": {}},
    ]
    result = correlate(events)
    assert result["a"]["sample_count"] == 2
    assert result["a"]["gpu_utilization_peak"] == 90.0
    assert result["a"]["mem_available_min_bytes"] == 50.0
    assert result["b"]["sample_count"] == 1

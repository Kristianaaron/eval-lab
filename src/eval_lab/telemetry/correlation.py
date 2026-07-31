"""Per-node telemetry correlation and raw-timestamp timing verification (spec 15.2, 15.3).

``verify_timing`` recomputes time-to-first-token and decode throughput purely
from the raw timestamped trace events (``model_request`` / ``token_event`` /
``model_completion``) — the Phase 3 exit gate ("TTFT and decode throughput are
verified against raw timestamps"). ``correlate`` groups periodic
``resource_sample`` events by node id into a per-node peak view.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

NODE_FALLBACK = "local"


def parse_events(trace_path: str | Path) -> list[dict[str, Any]]:
    """Parse an append-only JSONL trace into a list of event dicts."""
    events: list[dict[str, Any]] = []
    with open(trace_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _ns(event: dict[str, Any]) -> float:
    # The recorder stamps time_monotonic_ns at the event's top level.
    return float(event.get("time_monotonic_ns") or 0.0)


def verify_timing(events: list[dict[str, Any]], tolerance_s: float = 0.25) -> dict[str, Any]:
    """Recompute TTFT/decode from raw trace timestamps and compare vs. adapter report.

    Returns a dict with the raw-derived split, the adapter-reported split, and
    agreement booleans. Returns ``available: False`` when no tokens were traced.
    """
    request_ts: float | None = None
    token_ts: list[float] = []
    reported: dict[str, Any] = {}

    for ev in events:
        etype = ev.get("event_type")
        ts = _ns(ev)
        payload = ev.get("payload") or {}
        if etype == "model_request" and request_ts is None:
            request_ts = ts
        elif etype == "token_event":
            token_ts.append(float(payload.get("wall_time_ns", ts)))
        elif etype == "model_completion":
            reported = {
                "ttft_s": payload.get("ttft_s"),
                "decode_duration_s": payload.get("decode_duration_s"),
                "decode_tokens_per_s": payload.get("decode_tokens_per_s"),
                "completion_tokens": payload.get("completion_tokens"),
            }

    computed: dict[str, Any] = {"available": False, "reported": reported}
    if request_ts is None or not token_ts:
        return computed

    token_ts.sort()
    ttft_s = (token_ts[0] - request_ts) / 1e9
    n = len(token_ts)
    if n >= 2:
        decode_s = (token_ts[-1] - token_ts[0]) / 1e9
        decode_tps = (n - 1) / decode_s if decode_s > 0 else None
    else:
        decode_s = None
        decode_tps = None

    computed.update(
        {
            "available": True,
            "ttft_s": round(ttft_s, 6),
            "decode_duration_s": round(decode_s, 6) if decode_s is not None else None,
            "decode_tokens_per_s": round(decode_tps, 3) if decode_tps is not None else None,
            "token_count": n,
        }
    )

    rep_ttft = reported.get("ttft_s")
    if rep_ttft is not None:
        computed["ttft_agrees"] = abs(ttft_s - rep_ttft) <= tolerance_s
    rep_tps = reported.get("decode_tokens_per_s")
    if rep_tps is not None and decode_tps is not None:
        computed["decode_tps_agrees"] = abs(decode_tps - rep_tps) <= max(1.0, float(rep_tps) * 0.25)
    return computed


def correlate(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group ``resource_sample`` events by node_id into per-node peak views."""
    nodes: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        if ev.get("event_type") != "resource_sample":
            continue
        payload = ev.get("payload") or {}
        node = str(payload.get("node_id") or NODE_FALLBACK)
        nodes.setdefault(node, []).append(payload)

    result: dict[str, dict[str, Any]] = {}
    for node, samples in nodes.items():
        gpu_util = [
            float(g["utilization_gpu"])
            for s in samples
            for g in (s.get("nvidia") or [])
            if isinstance(g, dict) and isinstance(g.get("utilization_gpu"), (int, float))
        ]
        gpu_mem = [
            float(g["memory_used_mib"])
            for s in samples
            for g in (s.get("nvidia") or [])
            if isinstance(g, dict) and isinstance(g.get("memory_used_mib"), (int, float))
        ]
        avail = [
            float(s["system"]["mem_available_bytes"])
            for s in samples
            if isinstance(s.get("system"), dict)
            and isinstance(s["system"].get("mem_available_bytes"), (int, float))
        ]
        result[node] = {
            "node_id": node,
            "sample_count": len(samples),
            "gpu_utilization_peak": round(max(gpu_util), 1) if gpu_util else None,
            "gpu_memory_used_peak_mib": round(max(gpu_mem), 1) if gpu_mem else None,
            "mem_available_min_bytes": min(avail) if avail else None,
        }
    return result

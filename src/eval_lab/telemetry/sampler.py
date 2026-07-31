"""Sampler: periodic telemetry capture with monotonic timestamps (spec 15.3, 15.5).

Samples all collectors on a fixed interval and emits ``resource_sample`` trace
events through the run's TraceRecorder (spec 6.5), so every sample carries a
monotonic sequence number and links to the run id. The sampler keeps bounded
overhead: it runs on a single daemon thread and tolerates collector failures
without corrupting the run record.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from eval_lab.telemetry import collectors
from eval_lab.traces.recorder import TraceRecorder

Emit = Callable[[str, dict[str, Any]], None]


class TelemetrySampler:
    """Samples collectors on an interval and emits each snapshot via a callback."""

    def __init__(
        self,
        *,
        interval_s: float = 1.0,
        emit: Emit | None = None,
        label: str = "resource_sample",
        node_id: str | None = None,
    ) -> None:
        self.interval_s = interval_s
        self.emit = emit
        self.label = label
        self.node_id = node_id
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.samples: list[dict[str, Any]] = []

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="telemetry-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval_s * 2 + 1)

    def _loop(self) -> None:
        while not self._stop.is_set():
            payload = self.sample()
            self.samples.append(payload)
            if self.emit:
                self.emit(self.label, payload)
            self._stop.wait(self.interval_s)

    def sample(self) -> dict[str, Any]:
        now = time.monotonic_ns()
        return {
            "time_monotonic_ns": now,
            "node_id": self.node_id,
            "system": collectors.collect_system(),
            "process": collectors.collect_process(),
            "nvme": collectors.collect_nvme(),
            "network": collectors.collect_network(),
            "nvidia": collectors.collect_nvidia(),
        }

    def summary(self) -> dict[str, Any]:
        """Aggregate sampled values to a point-in-time best estimate."""
        if not self.samples:
            return {}
        gpu = _latest_nonempty(self.samples, "nvidia")
        return {
            "node_id": self.node_id,
            "sample_count": len(self.samples),
            "gpu_utilization_peak": _max_nested_float(gpu, "utilization_gpu"),
            "gpu_memory_used_peak_mib": _max_nested_float(gpu, "memory_used_mib"),
            "mem_available_bytes": _latest_system_field(self.samples, "mem_available_bytes"),
            "load_avg_last": _latest_system_load(self.samples),
        }


def attach_to_recorder(
    sampler: TelemetrySampler,
    recorder: TraceRecorder,
    *,
    node_id: str | None = None,
    interval_s: float | None = None,
) -> TelemetrySampler:
    """Wire a sampler to record ``resource_sample`` trace events for a run.

    The sampler is started (if not already) and stopped *not* here — the caller
    owns lifecycle so the run can attach mid-execution and detach at the end.
    """
    if node_id is not None:
        sampler.node_id = node_id
    if interval_s is not None:
        sampler.interval_s = interval_s
    sampler.emit = lambda event_type, payload: recorder.record(event_type, payload)
    sampler.start()
    return sampler


def _latest_nonempty(snapshots: list[dict[str, Any]], key: str) -> Any:
    for s in reversed(snapshots):
        v = s.get(key)
        if v not in (None, [], {}):
            return v
    return None


def _max_nested_float(value: Any, field: str) -> float | None:
    if not isinstance(value, list):
        return None
    vals: list[float] = []
    for item in value:
        if isinstance(item, dict) and isinstance(item.get(field), (int, float)):
            vals.append(float(item[field]))
    return max(vals) if vals else None


def _latest_system_field(snapshots: list[dict[str, Any]], field: str) -> float | None:
    for s in reversed(snapshots):
        sysv = s.get("system") or {}
        v = sysv.get(field)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _latest_system_load(snapshots: list[dict[str, Any]]) -> list[float] | None:
    for s in reversed(snapshots):
        sysv = s.get("system") or {}
        load = sysv.get("load_avg")
        if isinstance(load, list) and load:
            return [float(x) for x in load]
    return None

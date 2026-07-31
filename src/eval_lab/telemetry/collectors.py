"""System, process, NVMe, network and NVIDIA collectors (spec 15.2).

Every collector returns a flat dict of metrics. When a metric cannot be read it
must be stored as ``None`` (never fabricate a value) so runs are not corrupted
by missing hardware (spec 15.3).
"""

from __future__ import annotations

import os
import shutil
from typing import Any


def _null(reason: str) -> dict[str, Any]:
    return {"available": False, "reason": reason}


# ---------------------------------------------------------------------------
# System-level metrics (host CPU / memory) from /proc and os.
# ---------------------------------------------------------------------------


def collect_system() -> dict[str, Any]:
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            meminfo = {}
            for line in fh:
                parts = line.split()
                if parts:
                    meminfo[parts[0].rstrip(":")] = int(parts[1]) * 1024
        mem_total = meminfo.get("MemTotal")
        mem_available = meminfo.get("MemAvailable")
        metric = {
            "available": True,
            "cpu_count": os.cpu_count(),
            "load_avg": [round(x, 2) for x in os.getloadavg()],
            "mem_total_bytes": mem_total,
            "mem_available_bytes": mem_available,
            "mem_used_bytes": (
                (mem_total - mem_available) if (mem_total and mem_available) else None
            ),
        }
        return metric
    except Exception as exc:
        return {**_null("system collection failed"), "reason": str(exc)}


# ---------------------------------------------------------------------------
# Process metrics for our own pid and children.
# ---------------------------------------------------------------------------


def collect_process(pid: int | None = None) -> dict[str, Any]:
    pid = pid or os.getpid()
    try:
        status: dict[str, Any] = {}
        with open(f"/proc/{pid}/status", encoding="utf-8") as fh:
            for line in fh:
                if ":" in line:
                    k, _, v = line.partition(":")
                    status[k.strip()] = v.strip()
        rss = status.get("VmRSS")
        rss_bytes = int(rss.split()[0]) * 1024 if rss else None
        return {
            "available": True,
            "pid": pid,
            "threads": int(status.get("Threads") or 0),
            "vmrss_bytes": rss_bytes,
            "cpu_utime_s": status.get("utime"),
            "cpu_stime_s": status.get("stime"),
        }
    except Exception as exc:
        return {**_null("process collection failed"), "reason": str(exc)}


# ---------------------------------------------------------------------------
# NVMe disk metrics from /sys/block/*/stat (read/write sectors + ticks).
# ---------------------------------------------------------------------------


def _sysfs_metric(name: str) -> dict[str, Any]:
    metric: dict[str, Any] = {"available": False, "reason": f"{name} not found"}
    if not os.path.exists(name):
        return metric
    try:
        with open(name, encoding="utf-8") as fh:
            values = [int(v) for v in fh.read().split()]
        metric.update(
            {
                # Linux stat: [read_completed, read_merged, read_sectors,
                # read_ticks, write_completed, write_merged, write_sectors,
                # write_ticks, ...]
                "available": True,
                "read_sectors": values[2] if len(values) > 2 else None,
                "read_ticks_ms": values[3] if len(values) > 3 else None,
                "write_sectors": values[6] if len(values) > 6 else None,
                "write_ticks_ms": values[7] if len(values) > 7 else None,
            }
        )
    except Exception as exc:
        metric = {**_null("nvme read failed"), "reason": str(exc)}
    return metric


def collect_nvme() -> list[dict[str, Any]]:
    # Handles both named (nvme0n1) and virtual (sda) block devices.
    devices = (
        [d for d in os.listdir("/sys/block") if d.startswith(("nvme", "sd"))]
        if os.path.isdir("/sys/block")
        else []
    )
    if not devices:
        return [_null("no block devices")]
    out = []
    for dev in sorted(devices):
        m = _sysfs_metric(f"/sys/block/{dev}/stat")
        m["device"] = dev
        out.append(m)
    return out


# ---------------------------------------------------------------------------
# Network metrics from /proc/net/dev and sysfs counters.
# ---------------------------------------------------------------------------


def collect_network(interface: str | None = None) -> list[dict[str, Any]]:
    try:
        with open("/proc/net/dev", encoding="utf-8") as fh:
            lines = fh.readlines()[2:]
        interfaces = []
        for line in lines:
            name, _, data = line.partition(":")
            name = name.strip()
            fields = data.split()
            if len(fields) < 10:
                continue
            if interface and name != interface:
                continue
            interfaces.append(
                {
                    "interface": name,
                    "available": True,
                    "rx_bytes": int(fields[0]),
                    "rx_packets": int(fields[1]),
                    "tx_bytes": int(fields[8]),
                    "tx_packets": int(fields[9]),
                }
            )
        return interfaces or [_null("no interfaces")]
    except Exception as exc:
        return [_null(f"network collection failed: {exc}")]


# ---------------------------------------------------------------------------
# NVIDIA GPU metrics via nvidia-smi (arm64 Spark; may be pynvml-able later).
# ---------------------------------------------------------------------------


def collect_nvidia() -> list[dict[str, Any]]:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return [_null("nvidia-smi not installed")]
    import subprocess

    try:
        proc = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        return [_null(f"nvidia-smi error: {exc}")]
    if proc.returncode != 0:
        return [_null(f"nvidia-smi returned {proc.returncode}: {proc.stderr.strip()}")]
    gpus = []
    for line in proc.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 7:
            gpus.append(
                {
                    "available": True,
                    "index": parts[0],
                    "name": parts[1],
                    "utilization_gpu": _float(parts[2]),
                    "memory_used_mib": _float(parts[3]),
                    "memory_total_mib": _float(parts[4]),
                    "temperature_c": _float(parts[5]),
                    "power_draw_w": _float(parts[6]),
                }
            )
    return gpus or [_null("no GPU rows returned")]


def _float(v: str) -> float | None:
    try:
        return float(v)
    except ValueError:
        return None

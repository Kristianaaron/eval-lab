"""Environment/hardware status service (spec 2.1; correction #6).

Operational facts the Overview needs, served from code rather than hard-coded
in the view. Real per-node telemetry is an open dependency; this returns the
configured target envelope plus best-effort readable values.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass

_GIB = 1024**3


@dataclass(frozen=True)
class EnvironmentStatus:
    software_version: str
    nodes: int
    unified_memory_gb: float
    reserved_system_gb: float
    nvme_available_bytes: int | None = None
    gpu_present: bool | None = None


def environment_status(
    *,
    software_version: str = "eval-lab 0.9.0-GUI",
    nodes: int = 2,
    unified_memory_gb: float = 256.0,
    reserved_system_gb: float = 0.0,
) -> EnvironmentStatus:
    nvme = shutil.disk_usage("/").free if hasattr(shutil, "disk_usage") else None
    return EnvironmentStatus(
        software_version=software_version,
        nodes=nodes,
        unified_memory_gb=unified_memory_gb,
        reserved_system_gb=reserved_system_gb,
        nvme_available_bytes=nvme,
        gpu_present=_has_nvidia_gpu(),
    )


def _has_nvidia_gpu() -> bool | None:
    try:
        return os.path.isdir("/proc/driver/nvidia") or bool(shutil.which("nvidia-smi"))
    except Exception:  # pragma: no cover - best effort
        return None

"""Atlas bridge import records (eval-lab consumer side of the manifest bridge).

These are eval-lab's own persisted representation of an imported atlas run. The
structured keep-map data reuses the reserved atlas schemas (``UnitKeepMap`` /
``KeepMapEntry`` / ``UnitIdentity``) so a prune topology is auditable per unit;
the raw manifest, saliency rows and derivative payload are retained verbatim for
the detail view.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from eval_lab.schemas.atlas import UnitKeepMap


class AtlasPlanImport(BaseModel):
    """One candidate plan from ``plans.json`` plus its per-layer keep-maps."""

    model_config = ConfigDict(extra="forbid")

    name: str
    strategy: str | None = None
    keep_per_layer: int | None = None
    kept_per_layer: dict[str, int] = Field(default_factory=dict)
    keep_maps: list[UnitKeepMap] = Field(default_factory=list)


class AtlasBridgeImport(BaseModel):
    """A persisted atlas import, keyed by ``run_id``."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    arch: str | None = None
    status: str | None = None
    n_tasks: int | None = None
    n_plans: int = 0
    evidence_present: list[str] = Field(default_factory=list)
    has_derivative: bool = False
    manifest: dict[str, Any] = Field(default_factory=dict)
    saliency: list[dict[str, Any]] = Field(default_factory=list)
    plans: list[AtlasPlanImport] = Field(default_factory=list)
    derivative: dict[str, Any] | None = None
    imported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

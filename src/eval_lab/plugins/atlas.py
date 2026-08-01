"""Atlas plugin: bridge the model-atlas engine into eval-lab (ecosystem glue).

model-atlas is a separate application and repo. This plugin lets the eval
harness discover, open, and exchange data with it:

- Launch/health: `/api/atlas` (JSON), `/atlas` (redirect), and the `eval-lab
  atlas` CLI command.
- Data pipeline (native): export the eval-lab task/label corpus for Atlas
  calibration, and import derivatives/atlas findings back for hold-out eval.

The Atlas dashboard URL is configurable via `MODEL_ATLAS_URL`; it defaults to
this Spark's Tailnet address where the Atlas dashboard serves on port 8200.
"""

from __future__ import annotations

import os
import urllib.request
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

    _App = FastAPI
else:
    _App = Any

DEFAULT_ATLAS_URL = os.environ.get("MODEL_ATLAS_URL", "http://100.96.194.44:8200/")
# Shared interop directory (JSON manifests both platforms read/write).
PIPELINE_ROOT = os.environ.get("ATLAS_PIPELINE_ROOT", "/tmp/atlas-pipeline")


def atlas_dashboard_url() -> str:
    return DEFAULT_ATLAS_URL


def check_atlas(url: str | None = None, timeout: float = 2.0) -> dict[str, Any]:
    """Return {url, reachable, http_status, error} for the Atlas dashboard."""
    target = url or atlas_dashboard_url()
    try:
        with urllib.request.urlopen(target, timeout=timeout) as resp:  # noqa: S310
            return {"url": target, "reachable": True, "http_status": resp.status}
    except Exception as exc:  # noqa: BLE001
        return {"url": target, "reachable": False, "http_status": None, "error": str(exc)}


def register_atlas_routes(app: _App) -> None:
    """Attach Atlas discovery/link routes to the eval-lab FastAPI dashboard."""
    from fastapi.responses import RedirectResponse

    @app.get("/api/atlas", tags=["atlas"])
    def api_atlas() -> dict[str, Any]:
        """Return the Atlas dashboard URL and whether it is reachable."""
        return check_atlas()

    @app.get("/atlas", include_in_schema=True, tags=["atlas"])
    def atlas_redirect() -> RedirectResponse:
        """Open the Atlas engine (redirect to the model-atlas dashboard)."""
        return RedirectResponse(atlas_dashboard_url())

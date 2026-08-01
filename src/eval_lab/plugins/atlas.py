"""Atlas plugin: native integration of the model-atlas engine into eval-lab.

Provides a persistent connection between the two platforms (an ecosystem, not a
link): detect whether Atlas is installed, guide a new user through install, let
them connect to a running Atlas dashboard (validated + persisted), and surface
a connected/native state. Data exchange (eval tasks -> Atlas calibration;
derivatives -> eval hold-out) rides the same plugin.

Connection config persists on disk so "connected" survives dashboard restarts.
"""

from __future__ import annotations

import importlib.util
import json
import os
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from fastapi import FastAPI

    _App = FastAPI
else:
    _App = Any

DEFAULT_ATLAS_URL = os.environ.get("MODEL_ATLAS_URL", "http://127.0.0.1:8200/")
CONNECTION_FILE = os.environ.get(
    "ATLAS_CONNECTION_FILE", str(Path.home() / ".eval-lab" / "atlas_connection.json")
)


def model_atlas_installed() -> bool:
    """Whether the model-atlas package is importable on this host."""
    return importlib.util.find_spec("model_atlas") is not None


def atlas_dashboard_url() -> str:
    cfg = _read_config()
    return cfg.get("url") or DEFAULT_ATLAS_URL


def check_atlas(url: str | None = None, timeout: float = 2.0) -> dict[str, Any]:
    """Return {url, reachable, http_status, error}."""
    target = url or atlas_dashboard_url()
    try:
        with urllib.request.urlopen(target, timeout=timeout) as resp:  # noqa: S310
            return {"url": target, "reachable": True, "http_status": resp.status}
    except Exception as exc:  # noqa: BLE001
        return {"url": target, "reachable": False, "http_status": None, "error": str(exc)}


# -- connection persistence ---------------------------------------------------


def _read_config() -> dict[str, str]:
    try:
        return cast(dict[str, str], json.loads(Path(CONNECTION_FILE).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def _write_config(url: str) -> None:
    Path(CONNECTION_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(CONNECTION_FILE).write_text(json.dumps({"url": url}), encoding="utf-8")


def _clear_config() -> None:
    import contextlib

    with contextlib.suppress(OSError):
        Path(CONNECTION_FILE).unlink()


def connection_status() -> dict[str, Any]:
    """Overall integration status driving the UI: installed / connected / reachable."""
    cfg = _read_config()
    installed = model_atlas_installed()
    if not installed:
        return {
            "installed": False,
            "connected": False,
            "reachable": False,
            "url": DEFAULT_ATLAS_URL,
        }
    check = check_atlas(cfg.get("url") or None)
    return {
        "installed": True,
        "connected": bool(cfg.get("url")),
        "reachable": check["reachable"],
        "http_status": check["http_status"],
        "url": check["url"],
    }


def connect(url: str, timeout: float = 2.0) -> dict[str, Any]:
    """Validate an Atlas dashboard URL and persist the connection if reachable."""
    target = (url or "").strip()
    if not target.endswith("/"):
        target += "/"
    if not target.startswith(("http://", "https://")):
        target = "http://" + target
    check = check_atlas(target, timeout=timeout)
    if check["reachable"]:
        _write_config(target)
    status = connection_status()
    status["error"] = None if check["reachable"] else check.get("error")
    return status


def disconnect() -> dict[str, Any]:
    _clear_config()
    return connection_status()


def install_instructions() -> dict[str, str]:
    return {
        "package": "model-atlas",
        "home": "https://github.com/Kristianaaron/model-atlas",
        "install_command": "pip install model-atlas",
        "serve_command": (
            "model-atlas dashboard --out site/index.html; "
            "python -m http.server 8200 --directory site"
        ),
        "connect_url_hint": "http://127.0.0.1:8200/",
    }


# -- FastAPI route registration -----------------------------------------------


def register_atlas_routes(app: _App) -> None:
    """Attach Atlas integration routes (status / connect / disconnect / install)."""
    from fastapi.responses import RedirectResponse

    @app.get("/api/atlas/install", tags=["atlas"])
    def atlas_install() -> dict[str, Any]:
        return install_instructions()

    @app.get("/api/atlas", tags=["atlas"])
    def api_atlas() -> dict[str, Any]:
        return connection_status()

    @app.post("/api/atlas/connect", tags=["atlas"])
    def atlas_connect(url: str = "") -> dict[str, Any]:
        return connect(url)

    @app.post("/api/atlas/disconnect", tags=["atlas"])
    def atlas_disconnect() -> dict[str, Any]:
        return disconnect()

    @app.get("/atlas", include_in_schema=True, tags=["atlas"])
    def atlas_redirect() -> RedirectResponse:
        """Open the connected Atlas engine (redirect to its dashboard)."""
        return RedirectResponse(atlas_dashboard_url())

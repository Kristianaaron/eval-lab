"""Dashboard (web UI) package: read-only FastAPI server over run data."""

from __future__ import annotations

from eval_lab.dashboard.api import create_app

__all__ = ["create_app"]

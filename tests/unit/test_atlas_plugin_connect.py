"""Atlas plugin connection: reachability-based, no install-gate on eval-lab."""

from __future__ import annotations

from eval_lab.plugins import atlas as atlas_plugin
from eval_lab.plugins.atlas import connection_status


def test_connected_when_service_reachable_even_if_package_absent(monkeypatch) -> None:
    # The Atlas profiler runs as a separate served app; eval-lab connects over
    # HTTP, so it must NOT require model-atlas importable in eval-lab's venv.
    monkeypatch.setattr(atlas_plugin, "model_atlas_installed", lambda: False)
    monkeypatch.setattr(
        atlas_plugin,
        "check_atlas",
        lambda url, timeout=2.0: {
            "url": url,
            "reachable": True,
            "http_status": 200,
            "error": None,
        },
    )
    status = connection_status()
    assert status["installed"] is False
    assert status["connected"] is True  # usable even though not pip-installed
    assert status["reachable"] is True


def test_not_connected_when_service_down(monkeypatch) -> None:
    monkeypatch.setattr(atlas_plugin, "model_atlas_installed", lambda: True)
    monkeypatch.setattr(
        atlas_plugin,
        "check_atlas",
        lambda url, timeout=2.0: {
            "url": url,
            "reachable": False,
            "http_status": None,
            "error": "connection refused",
        },
    )
    status = connection_status()
    assert status["connected"] is False
    assert status["reachable"] is False

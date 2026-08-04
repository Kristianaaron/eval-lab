"""On-disk workspace for M3 atlas runs (``atlas_out/atlas_runs/<id>/``).

Matches the on-disk contract the atlas-bridge consumer imports, so real M3 runs
light up in the Explorer and Experiment surfaces unchanged. Also owns the
the recovery checkpoint: per-layer partials are written as each layer completes so a
paused/interrupted job resumes from the last finished layer.

Files:
- ``run_manifest.json``, ``layer_saliency.json``, ``plans.json``  (bridge contract)
- ``saliency_by_label.json``, ``keep_maps.json``, ``trace.jsonl``   (M3 detail)
- ``source_model/config.json`` + ``weights.json``                   (auditable mini-MoE)
- ``_checkpoint.json`` + ``working/layer_{n}.json``                (recovery state)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval_lab.atlas.tracer import LayerResult


class AtlasRunStore:
    def __init__(self, out_root: str | Path) -> None:
        self.out_root = Path(out_root)
        self.runs_dir = self.out_root / "atlas_runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def _write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _read_json(self, path: Path) -> Any | None:
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    # -- recovery state -----------------------------------------------------
    def save_last_layer(self, run_id: str, layer: int) -> None:
        self._write_json(self.run_dir(run_id) / "_checkpoint.json", {"last_completed_layer": layer})

    def load_last_layer(self, run_id: str) -> int | None:
        data = self._read_json(self.run_dir(run_id) / "_checkpoint.json")
        if isinstance(data, dict):
            v = data.get("last_completed_layer")
            if isinstance(v, int):
                return v
        return None

    def save_layer_partial(self, run_id: str, layer_result: LayerResult) -> None:
        self._write_json(
            self.run_dir(run_id) / "working" / f"layer_{layer_result.layer}.json",
            layer_result.to_dict(),
        )

    def load_layer_partials(self, run_id: str) -> list[LayerResult]:
        working = self.run_dir(run_id) / "working"
        results: list[LayerResult] = []
        if not working.is_dir():
            return results
        for path in sorted(working.glob("layer_*.json")):
            data = self._read_json(path)
            if data is not None:
                results.append(LayerResult.from_dict(data))
        return sorted(results, key=lambda r: r.layer)

    # -- source model -------------------------------------------------------
    def write_source_model(self, run_id: str, model: Any) -> None:
        model.write(self.run_dir(run_id) / "source_model")

    # -- final artifacts ----------------------------------------------------
    def write_artifacts(
        self,
        run_id: str,
        *,
        manifest: dict[str, Any],
        saliency_rows: list[dict[str, Any]],
        saliency_by_label: list[dict[str, Any]],
        plans: list[dict[str, Any]],
        keep_maps: list[dict[str, Any]],
        trace_rows: list[dict[str, Any]],
    ) -> None:
        run = self.run_dir(run_id)
        self._write_json(run / "run_manifest.json", manifest)
        self._write_json(run / "layer_saliency.json", saliency_rows)
        self._write_json(run / "saliency_by_label.json", saliency_by_label)
        self._write_json(run / "plans.json", plans)
        self._write_json(run / "keep_maps.json", keep_maps)
        (run / "trace.jsonl").write_text(
            "\n".join(json.dumps(r) for r in trace_rows), encoding="utf-8"
        )

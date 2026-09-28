"""Benchmark scorecard: one model, every dimension, straight from the run index.

A scorecard is the standalone-benchmark answer to "how good is this model?":
per-domain pass rates and mean scores over the latest run of every task,
perplexity per corpus, and the deep-coding / long-context sub-benchmarks
called out separately because they are the ones compression damages first.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from eval_lab.schemas.models import TaskSpec
from eval_lab.storage.sqlite import RunStore
from eval_lab.tasks.loader import load_task_yaml

# Standard benchmark groups (suite family "benchmark"). Order = display order.
BENCHMARK_GROUPS: dict[str, dict[str, Any]] = {
    "core": {
        "name": "Core capabilities",
        "suite": "configs/suites/benchmark-core.yaml",
        "description": (
            "Reasoning, mathematics, instruction following, tool use and frontend basics."
        ),
    },
    "coding_deep": {
        "name": "Deep coding",
        "suite": "configs/suites/benchmark-coding-deep.yaml",
        "description": (
            "Multi-part specifications with 15-35 hidden tests each, plus "
            "repository-level agentic fixes and refactors."
        ),
    },
    "long_context": {
        "name": "Long context",
        "suite": "configs/suites/benchmark-long-context.yaml",
        "description": (
            "Multi-hop retrieval, aggregation and bug hunting over 8k-64k token documents."
        ),
    },
    "perplexity": {
        "name": "Perplexity",
        "suite": "configs/suites/benchmark-perplexity.yaml",
        "description": (
            "Intrinsic language-modelling quality (perplexity, bits/byte) over fixed corpora."
        ),
    },
}


@dataclass
class DimensionStats:
    label: str
    task_count: int = 0
    run_count: int = 0
    mean_score: float | None = None
    pass_rate: float | None = None
    tasks: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class Scorecard:
    model_id: str
    total_runs: int
    scored_tasks: int
    overall_score: float | None
    overall_pass_rate: float | None
    groups: dict[str, DimensionStats]
    domains: dict[str, DimensionStats]
    perplexity: dict[str, dict[str, Any]]
    missing_groups: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "total_runs": self.total_runs,
            "scored_tasks": self.scored_tasks,
            "overall_score": self.overall_score,
            "overall_pass_rate": self.overall_pass_rate,
            "groups": {k: asdict(v) for k, v in self.groups.items()},
            "domains": {k: asdict(v) for k, v in self.domains.items()},
            "perplexity": self.perplexity,
            "missing_groups": self.missing_groups,
        }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def index_tasks(tasks_dir: str | Path = "tasks") -> dict[str, TaskSpec]:
    index: dict[str, TaskSpec] = {}
    for p in Path(tasks_dir).rglob("task.yaml"):
        try:
            t = load_task_yaml(p)
        except Exception:
            continue
        index[t.id] = t
    return index


def suite_task_ids(suite_path: str | Path) -> list[str]:
    from eval_lab.tasks.loader import load_suite_yaml

    p = Path(suite_path)
    if not p.is_file():
        return []
    try:
        return [ref.task_id for ref in load_suite_yaml(p).tasks]
    except Exception:
        return []


def _finalize(stats: DimensionStats) -> DimensionStats:
    scored = [t["score"] for t in stats.tasks.values() if t.get("score") is not None]
    passed = [t["passed"] for t in stats.tasks.values() if t.get("passed") is not None]
    stats.task_count = len(stats.tasks)
    stats.mean_score = round(sum(scored) / len(scored), 4) if scored else None
    stats.pass_rate = round(sum(1 for p in passed if p) / len(passed), 4) if passed else None
    return stats


def build_scorecard(
    store: RunStore,
    model_id: str,
    *,
    runs_root: str | Path = "runs",
    tasks_dir: str | Path = "tasks",
    suites_dir: str | Path = "configs/suites",
) -> Scorecard:
    """Latest completed run per task for ``model_id`` → grouped statistics."""
    tasks = index_tasks(tasks_dir)
    runs = [r for r in store.list_runs(limit=100_000) if r.get("model_id") == model_id]
    # Newest first from the store; keep the latest completed run per task.
    latest: dict[str, dict[str, Any]] = {}
    for r in runs:
        tid = str(r.get("task_id") or "")
        if not tid or r.get("status") != "completed" or tid in latest:
            continue
        latest[tid] = r

    base = Path(runs_root)
    domains: dict[str, DimensionStats] = {}
    perplexity: dict[str, dict[str, Any]] = {}
    per_task: dict[str, dict[str, Any]] = {}
    for tid, r in latest.items():
        run_id = str(r["run_id"])
        run_dir = base / run_id
        manifest = _read_json(run_dir / "manifest.json")
        score = r.get("aggregate_score")
        entry = {
            "run_id": run_id,
            "score": float(score) if isinstance(score, (int, float)) else None,
            "passed": bool(r.get("passed")) if r.get("passed") is not None else None,
            "created_at": r.get("created_at"),
            "duration_s": manifest.get("duration_s"),
        }
        spec = tasks.get(tid)
        if spec is not None and spec.execution.runner == "perplexity":
            metrics = (
                manifest.get("metrics") or _read_json(run_dir / "result.json").get("metrics") or {}
            )
            perplexity[tid] = {
                "run_id": run_id,
                "name": spec.name,
                "perplexity": metrics.get("perplexity"),
                "bits_per_byte": metrics.get("bits_per_byte"),
                "bits_per_token": metrics.get("bits_per_token"),
                "tokens": metrics.get("tokens"),
                "windows": metrics.get("windows"),
                "created_at": r.get("created_at"),
            }
        per_task[tid] = entry
        for d in spec.labels.domains if spec else ["unknown"]:
            domains.setdefault(d, DimensionStats(label=d)).tasks[tid] = entry

    groups: dict[str, DimensionStats] = {}
    missing: list[str] = []
    for key, meta in BENCHMARK_GROUPS.items():
        suite_path = Path(meta["suite"])
        if not suite_path.is_absolute():
            suite_path = Path(suites_dir) / suite_path.name
        ids = suite_task_ids(suite_path)
        stats = DimensionStats(label=meta["name"])
        for tid in ids:
            if tid in per_task:
                stats.tasks[tid] = per_task[tid]
        groups[key] = _finalize(stats)
        if ids and not stats.tasks:
            missing.append(key)

    for dim in domains.values():
        _finalize(dim)
    scored = [t["score"] for t in per_task.values() if t["score"] is not None]
    passed = [t["passed"] for t in per_task.values() if t["passed"] is not None]
    return Scorecard(
        model_id=model_id,
        total_runs=len(runs),
        scored_tasks=len(per_task),
        overall_score=round(sum(scored) / len(scored), 4) if scored else None,
        overall_pass_rate=round(sum(1 for p in passed if p) / len(passed), 4) if passed else None,
        groups=groups,
        domains=dict(sorted(domains.items())),
        perplexity=perplexity,
        missing_groups=missing,
    )


def render_scorecard_markdown(card: Scorecard) -> str:
    lines = [f"# Benchmark scorecard — {card.model_id}", ""]
    lines.append(f"- runs: {card.total_runs}  · scored tasks: {card.scored_tasks}")
    overall = _fmt(card.overall_score)
    lines.append(f"- overall mean score: {overall}  · pass rate: {_pct(card.overall_pass_rate)}")
    lines += [
        "",
        "## Benchmark groups",
        "",
        "| group | tasks | mean score | pass rate |",
        "|---|---|---|---|",
    ]
    for key, g in card.groups.items():
        lines.append(
            f"| {g.label} ({key}) | {g.task_count} | {_fmt(g.mean_score)} | {_pct(g.pass_rate)} |"
        )
    if card.perplexity:
        lines += [
            "",
            "## Perplexity",
            "",
            "| corpus | perplexity | bits/byte | bits/token | tokens |",
            "|---|---|---|---|---|",
        ]
        for tid, p in card.perplexity.items():
            ppl, bpb = _fmt(p.get("perplexity"), 3), _fmt(p.get("bits_per_byte"), 4)
            bpt = _fmt(p.get("bits_per_token"), 4)
            lines.append(
                f"| {p.get('name') or tid} | {ppl} | {bpb} | {bpt} | {p.get('tokens') or '—'} |"
            )
    lines += [
        "",
        "## Domains",
        "",
        "| domain | tasks | mean score | pass rate |",
        "|---|---|---|---|",
    ]
    for d, s in card.domains.items():
        lines.append(f"| {d} | {s.task_count} | {_fmt(s.mean_score)} | {_pct(s.pass_rate)} |")
    if card.missing_groups:
        lines += ["", f"_No runs yet for: {', '.join(card.missing_groups)}_"]
    return "\n".join(lines) + "\n"


def _fmt(v: Any, nd: int = 3) -> str:
    return f"{v:.{nd}f}" if isinstance(v, (int, float)) else "—"


def _pct(v: Any) -> str:
    return f"{100 * v:.1f}%" if isinstance(v, (int, float)) else "—"

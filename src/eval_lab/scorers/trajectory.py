"""trajectory scorer: reason about agent behavior from trace events (spec 13.3)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from eval_lab.schemas.models import ScoreResult
from eval_lab.scorers.base import register_scorer

DIMENSIONS = (
    "tool_selection",
    "repeats_failed_action",
    "recovery",
    "verification",
    "plan_to_action",
    "unnecessary_actions",
    "destructive_actions",
)

# Tools whose use is treated as potentially destructive (can remove/overwrite
# workspace state) in the absence of per-call argument records.
_DESTRUCTIVE_TOOLS = {"shell"}

_VERIFY_TOOLS = {"file_read", "list_files"}
_WRITE_TOOLS = {"file_write"}

Scaler = Callable[[dict[str, Any]], tuple[float, bool, dict[str, Any]]]


class TrajectoryScorer:
    """Score an agent trajectory from ``run_dir/trace.jsonl``.

    Config:
        weights          per-dimension weights {dim: weight} (default 1.0).
        pass_threshold   composite threshold for ``passed`` (default 0.6).

    Each dimension is scored from *actual* trace events (``tool_result``,
    ``model_completion``, ``agent_turn_start``). Dimensions with no evidence are
    excluded from the composite mean and recorded in ``skipped_dimensions``
    rather than zeroed or errored. If no dimension has evidence the scorer
    reports ``error`` (it cannot score).
    """

    scorer_id = "trajectory"

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        pass_threshold: float = 0.6,
    ) -> None:
        self.weights = dict(weights or {})
        self.pass_threshold = pass_threshold

    def score(self, *, output: str, task: Any = None, run_dir: Any = None) -> ScoreResult:
        if run_dir is None:
            return ScoreResult(
                scorer_id=self.scorer_id,
                score=0.0,
                passed=False,
                error="trajectory scorer requires a run_dir",
                details={},
            )
        trace_path = Path(run_dir) / "trace.jsonl"
        if not trace_path.is_file():
            return ScoreResult(
                scorer_id=self.scorer_id,
                score=0.0,
                passed=False,
                error=f"trace.jsonl not found: {trace_path}",
                details={"trace": str(trace_path)},
            )
        try:
            events = _load_events(trace_path)
        except (OSError, json.JSONDecodeError) as exc:
            return ScoreResult(
                scorer_id=self.scorer_id,
                score=0.0,
                passed=False,
                error=f"failed to read trace: {exc}",
                details={"trace": str(trace_path)},
            )
        if not events:
            return ScoreResult(
                scorer_id=self.scorer_id,
                score=0.0,
                passed=False,
                error="no trajectory events to score",
                details={"trace": str(trace_path)},
            )

        metrics = _analyze(events)
        sub: dict[str, dict[str, Any]] = {}
        scored: list[str] = []
        for dim in DIMENSIONS:
            fn = _SCALERS[dim]
            s, evidence, detail = fn(metrics)
            sub[dim] = {"score": round(s, 4), "evidence": evidence, **detail}
            if evidence:
                scored.append(dim)

        if not scored:
            return ScoreResult(
                scorer_id=self.scorer_id,
                score=0.0,
                passed=False,
                error="no trajectory evidence to score",
                details={
                    "skipped_dimensions": list(DIMENSIONS),
                    "metrics": _metrics_summary(metrics),
                },
            )

        skipped = [d for d in DIMENSIONS if d not in scored]
        weight_sum = sum(self.weights.get(d, 1.0) for d in scored)
        composite = sum(self.weights.get(d, 1.0) * sub[d]["score"] for d in scored) / weight_sum
        passed = composite >= self.pass_threshold
        return ScoreResult(
            scorer_id=self.scorer_id,
            score=round(composite, 4),
            passed=passed,
            details={
                "composite": round(composite, 4),
                "pass_threshold": self.pass_threshold,
                "scored_dimensions": scored,
                "skipped_dimensions": skipped,
                "dimensions": {d: sub[d] for d in scored},
                "metrics": _metrics_summary(metrics),
            },
        )


# ---------------------------------------------------------------------------
# Trace parsing
# ---------------------------------------------------------------------------


def _load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events


def _analyze(events: list[dict[str, Any]]) -> dict[str, Any]:
    tools: list[dict[str, Any]] = []
    model_events = 0
    turn_events = 0
    for ev in events:
        et = ev.get("event_type")
        payload = ev.get("payload") or {}
        if et == "tool_result":
            tools.append(
                {
                    "tool": payload.get("tool"),
                    "ok": bool(payload.get("ok")),
                    "error": payload.get("error"),
                }
            )
        elif et == "model_completion":
            model_events += 1
        elif et == "agent_turn_start":
            turn_events += 1
    return {
        "tools": tools,
        "model_events": model_events,
        "turn_events": turn_events,
    }


def _metrics_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    tools = metrics["tools"]
    return {
        "tool_calls": len(tools),
        "model_completions": metrics["model_events"],
        "turns": metrics["turn_events"],
    }


# ---------------------------------------------------------------------------
# Per-dimension scalers. (score, evidence, detail) — evidence False => skipped.
# ---------------------------------------------------------------------------


def _tool_selection(metrics: dict[str, Any]) -> tuple[float, bool, dict[str, Any]]:
    tools = metrics["tools"]
    if not tools:
        return 0.0, False, {}
    ok = sum(1 for t in tools if t.get("ok"))
    return ok / len(tools), True, {"ok_calls": ok, "total_calls": len(tools)}


def _repeats_failed_action(metrics: dict[str, Any]) -> tuple[float, bool, dict[str, Any]]:
    tools = metrics["tools"]
    failures = sum(1 for t in tools if not t.get("ok"))
    if failures == 0:
        return 0.0, False, {}
    repeats = 0
    for i in range(1, len(tools)):
        same = tools[i].get("tool") == tools[i - 1].get("tool")
        if not tools[i].get("ok") and not tools[i - 1].get("ok") and same:
            repeats += 1
    score = max(0.0, 1.0 - repeats / failures)
    return (
        score,
        True,
        {
            "failures": failures,
            "repeats": repeats,
            "repeat_rate": round(repeats / failures, 4),
        },
    )


def _recovery(metrics: dict[str, Any]) -> tuple[float, bool, dict[str, Any]]:
    tools = metrics["tools"]
    failures = sum(1 for t in tools if not t.get("ok"))
    if failures == 0:
        return 0.0, False, {}
    recoveries = 0
    for i, t in enumerate(tools):
        if t.get("ok"):
            continue
        nxt = tools[i + 1] if i + 1 < len(tools) else None
        if nxt is not None and (nxt.get("ok") or nxt.get("tool") != t.get("tool")):
            recoveries += 1
    return (
        recoveries / failures,
        True,
        {
            "failures": failures,
            "recoveries": recoveries,
            "recovery_rate": round(recoveries / failures, 4),
        },
    )


def _verification(metrics: dict[str, Any]) -> tuple[float, bool, dict[str, Any]]:
    tools = metrics["tools"]
    write_indexes = [i for i, t in enumerate(tools) if t.get("tool") in _WRITE_TOOLS]
    if not write_indexes:
        return 0.0, False, {}
    verified = 0
    for wi in write_indexes:
        if any(t.get("tool") in _VERIFY_TOOLS for t in tools[wi + 1 :]):
            verified += 1
    return (
        verified / len(write_indexes),
        True,
        {"writes": len(write_indexes), "verified_writes": verified},
    )


def _plan_to_action(metrics: dict[str, Any]) -> tuple[float, bool, dict[str, Any]]:
    tools = metrics["tools"]
    if not tools:
        return 0.0, False, {}
    planned = 1.0 if metrics["model_events"] >= 1 else 0.0
    return planned, True, {"model_completions": metrics["model_events"], "tool_calls": len(tools)}


def _unnecessary_actions(metrics: dict[str, Any]) -> tuple[float, bool, dict[str, Any]]:
    tools = metrics["tools"]
    if not tools:
        return 0.0, False, {}
    redundant = 0
    for i in range(1, len(tools)):
        same = tools[i].get("tool") == tools[i - 1].get("tool")
        if tools[i].get("ok") and tools[i - 1].get("ok") and same:
            redundant += 1
    return (
        max(0.0, 1.0 - redundant / len(tools)),
        True,
        {"redundant_calls": redundant, "total_calls": len(tools)},
    )


def _destructive_actions(metrics: dict[str, Any]) -> tuple[float, bool, dict[str, Any]]:
    tools = metrics["tools"]
    if not tools:
        return 0.0, False, {}
    destructive = sum(1 for t in tools if t.get("tool") in _DESTRUCTIVE_TOOLS)
    return (
        1.0 - min(1.0, destructive / len(tools)),
        True,
        {
            "destructive_calls": destructive,
            "total_calls": len(tools),
        },
    )


_SCALERS: dict[str, Scaler] = {
    "tool_selection": _tool_selection,
    "repeats_failed_action": _repeats_failed_action,
    "recovery": _recovery,
    "verification": _verification,
    "plan_to_action": _plan_to_action,
    "unnecessary_actions": _unnecessary_actions,
    "destructive_actions": _destructive_actions,
}


register_scorer("trajectory", TrajectoryScorer)

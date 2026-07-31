"""Judge calibration against a human gold set (spec 14.3)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eval_lab.judges.adapter import LLMJudge, OfflineJudge  # noqa: F401 (types)
from eval_lab.judges.pairwise import order_bias_pp
from eval_lab.judges.protocol import (
    Judge,
    JudgeConfig,
    JudgeResult,
    JudgeRubric,
    JudgeThresholds,
)

# ---------------------------------------------------------------------------
# Gold set
# ---------------------------------------------------------------------------


@dataclass
class GoldEntry:
    task_instruction: str
    rubric: Any
    output: str
    dimension: str
    human_label: str
    human_score: float

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GoldEntry:
        return cls(
            task_instruction=str(d.get("task_instruction", "")),
            rubric=d.get("rubric", ""),
            output=str(d.get("output", "")),
            dimension=str(d.get("dimension", "")),
            human_label=str(d.get("human_label", "")),
            human_score=float(d.get("human_score", 0.0)),
        )


def load_gold_set(gold_dir: str | Path, dimension: str | None = None) -> list[GoldEntry]:
    """Load gold entries from every ``*.json`` under ``gold_dir``.

    Each file may be a single entry object or a list of entries. Entries are
    filtered to ``dimension`` when given.
    """
    root = Path(gold_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"gold dir not found: {root}")
    entries: list[GoldEntry] = []
    for p in sorted(root.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else [data]
        for it in items:
            entry = GoldEntry.from_dict(it)
            if dimension is None or entry.dimension == dimension:
                entries.append(entry)
    return entries


def load_judge_config(path: str | Path) -> JudgeConfig:
    import yaml

    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"judge config must be a mapping: {path}")
    return JudgeConfig.model_validate(raw)


# ---------------------------------------------------------------------------
# Agreement statistics
# ---------------------------------------------------------------------------


def exact_agreement(predictions: list[int], humans: list[int]) -> float:
    n = len(predictions)
    if n == 0:
        return 0.0
    return sum(1 for p, h in zip(predictions, humans, strict=True) if p == h) / n


def weighted_kappa(predictions: list[int], humans: list[int]) -> float:
    """Linear-weighted Cohen's kappa over ordinal level categories."""
    n = len(predictions)
    if n == 0:
        return 0.0
    levels = sorted(set(predictions) | set(humans))
    k = len(levels)
    if k <= 1:
        return 1.0
    idx = {lv: i for i, lv in enumerate(levels)}
    w = [[1.0 - abs(i - j) / (k - 1) for j in range(k)] for i in range(k)]
    matrix = [[0] * k for _ in range(k)]
    for p, h in zip(predictions, humans, strict=True):
        matrix[idx[p]][idx[h]] += 1
    po = 0.0
    for i in range(k):
        for j in range(k):
            po += matrix[i][j] * w[i][j]
    po /= n
    rows = [sum(r) for r in matrix]
    cols = [sum(matrix[i][j] for i in range(k)) for j in range(k)]
    pe = 0.0
    for i in range(k):
        for j in range(k):
            pe += (rows[i] * cols[j] / (n * n)) * w[i][j]
    denom = 1.0 - pe
    if denom <= 0.0:
        return 1.0
    return (po - pe) / denom


def pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    sx = math.sqrt(sum((v - mx) ** 2 for v in x) / n)
    sy = math.sqrt(sum((v - my) ** 2 for v in y) / n)
    if sx == 0.0 or sy == 0.0:
        return 0.0
    return sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / (n * sx * sy)


# ---------------------------------------------------------------------------
# Calibration report
# ---------------------------------------------------------------------------


@dataclass
class CalibrationReport:
    judge_id: str
    dimension: str
    kind: str
    n_entries: int
    agreement: float
    weighted_kappa: float
    fp: int
    fn: int
    fp_rate: float
    fn_rate: float
    order_bias_pp: float | None
    verbosity_bias: float
    self_preference: float | None
    repeat_consistency: float
    repeat_samples: int
    malformed_rate: float
    total_judge_calls: int
    verdict: str
    criterion_details: dict[str, Any] = field(default_factory=dict)
    raw_scores: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "judge_id": self.judge_id,
            "dimension": self.dimension,
            "kind": self.kind,
            "n_entries": self.n_entries,
            "agreement": round(self.agreement, 4),
            "weighted_kappa": round(self.weighted_kappa, 4),
            "false_positives": self.fp,
            "false_negatives": self.fn,
            "fp_rate": round(self.fp_rate, 4),
            "fn_rate": round(self.fn_rate, 4),
            "order_bias_pp": self.order_bias_pp,
            "verbosity_bias": round(self.verbosity_bias, 4),
            "self_preference": self.self_preference,
            "repeat_consistency": round(self.repeat_consistency, 4),
            "repeat_samples": self.repeat_samples,
            "malformed_rate": round(self.malformed_rate, 4),
            "total_judge_calls": self.total_judge_calls,
            "verdict": self.verdict,
            "criteria": self.criterion_details,
            "entries": self.raw_scores,
        }

    def to_markdown(self) -> str:
        lines: list[str] = []
        lines.append("# Judge Calibration Report")
        lines.append("")
        lines.append(f"- **Judge id:** `{self.judge_id}`")
        lines.append(f"- **Dimension:** `{self.dimension}`")
        lines.append(f"- **Judge kind:** `{self.kind}`")
        lines.append(f"- **Gold entries:** {self.n_entries}")
        lines.append(f"- **Verdict:** `{self.verdict}`")
        lines.append("")
        lines.append("## Metrics")
        lines.append("")
        lines.append("| Metric | Value | Target |")
        lines.append("|---|---|---|")
        agreement_min = self.criterion_details.get("agreement_min", 0.75)
        kappa_min = self.criterion_details.get("kappa_min", 0.60)
        order_pp = self.criterion_details.get("order_bias_pp", 5.0)
        malformed_max = self.criterion_details.get("malformed_max", 0.01)
        lines.append(f"| Exact agreement | {self.agreement:.3f} | >= {agreement_min:.2f} |")
        lines.append(f"| Weighted kappa | {self.weighted_kappa:.3f} | >= {kappa_min:.2f} |")
        lines.append(f"| False-positive rate | {self.fp_rate:.3f} ({self.fp}) | low |")
        lines.append(f"| False-negative rate | {self.fn_rate:.3f} ({self.fn}) | low |")
        ob = "n/a" if self.order_bias_pp is None else f"{self.order_bias_pp:.2f}pp"
        lines.append(f"| Pairwise order bias | {ob} | <= {order_pp:.0f}pp |")
        lines.append(f"| Verbosity bias | {self.verbosity_bias:.3f} | ~0 |")
        sp = self.self_preference if self.self_preference is not None else "n/a"
        lines.append(f"| Self-preference | {sp} | ~0 |")
        repeat_line = (
            f"| Repeat consistency | {self.repeat_consistency:.3f} "
            f"(n={self.repeat_samples}) | high |"
        )
        lines.append(repeat_line)
        malformed_line = (
            f"| Malformed-output rate | {self.malformed_rate:.4f} | < {malformed_max:.2f} |"
        )
        lines.append(malformed_line)
        lines.append("")
        lines.append("## Criteria")
        lines.append("")
        for k, v in sorted(self.criterion_details.items()):
            if k in ("agreement_min", "kappa_min", "order_bias_pp", "malformed_max"):
                continue
            lines.append(f"- **{k}:** {v}")
        lines.append("")
        lines.append(f"**Verdict: {self.verdict}**")
        return "\n".join(lines)


def write_calibration_report(report: CalibrationReport, out_dir: str | Path) -> Path:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    md_path = root / f"calibration_{report.judge_id}_{report.dimension}.md"
    json_path = root / f"calibration_{report.judge_id}_{report.dimension}.json"
    md_path.write_text(report.to_markdown() + "\n", encoding="utf-8")
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    json_path.write_text(payload, encoding="utf-8")
    return md_path


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_calibration(
    judge: Judge,
    gold_entries: list[GoldEntry],
    *,
    thresholds: JudgeThresholds | None = None,
    pairs: list[dict[str, Any]] | None = None,
    repeat_samples: int = 3,
) -> CalibrationReport:
    thr = thresholds or JudgeThresholds()
    rubric = getattr(judge, "config", None)
    judge_rubric: JudgeRubric | None = (
        getattr(rubric, "rubric", None) if rubric is not None else None
    )

    results: list[tuple[GoldEntry, JudgeResult]] = []
    for entry in gold_entries:
        jr = judge.judge(
            task_instruction=entry.task_instruction,
            rubric=entry.rubric or (judge_rubric or ""),
            output=entry.output,
            dimension=entry.dimension,
        )
        results.append((entry, jr))

    scored = [(e, jr) for e, jr in results if jr.error is None and jr.score is not None]
    n = len(scored)

    predictions: list[int] = []
    humans: list[int] = []
    lengths: list[float] = []
    residuals: list[float] = []
    fpos = 0
    fneg = 0
    raw: list[dict[str, Any]] = []
    for e, jr in scored:
        pred_level = jr.label_level
        human_level = _human_level(judge_rubric, e.human_score)
        predictions.append(pred_level)
        humans.append(human_level)
        pred_pass = jr.score >= thr.pass_threshold
        human_pass = e.human_score >= thr.pass_threshold
        if pred_pass and not human_pass:
            fpos += 1
        if not pred_pass and human_pass:
            fneg += 1
        lengths.append(float(len(e.output.split())))
        residuals.append(jr.score - e.human_score)
        raw.append(
            {
                "dimension": e.dimension,
                "judge_score": round(jr.score, 4),
                "judge_label": jr.label,
                "human_score": e.human_score,
                "human_label": e.human_label,
            }
        )

    agreement = exact_agreement(predictions, humans) if n else 0.0
    kappa = weighted_kappa(predictions, humans) if n else 0.0
    verbosity_bias = pearson(lengths, residuals) if n else 0.0

    # Repeat consistency: judge a subset twice and compare.
    repeat_ok = 0
    repeat_n = min(repeat_samples, len(gold_entries))
    for entry in gold_entries[:repeat_n]:
        first = judge.judge(
            task_instruction=entry.task_instruction,
            rubric=entry.rubric or (judge_rubric or ""),
            output=entry.output,
            dimension=entry.dimension,
        )
        second = judge.judge(
            task_instruction=entry.task_instruction,
            rubric=entry.rubric or (judge_rubric or ""),
            output=entry.output,
            dimension=entry.dimension,
        )
        if first.error is None and second.error is None and first.label_level == second.label_level:
            repeat_ok += 1
    repeat_consistency = repeat_ok / repeat_n if repeat_n else 1.0

    malformed_rate = _malformed_rate(judge)
    total_calls = _call_count(judge)
    ob = order_bias_pp(pairs or [])

    # Verdict (spec 14.3).
    if n == 0:
        verdict = "dimension-unscored"
    else:
        agg_pass = agreement >= thr.agreement_min or kappa >= thr.kappa_min
        order_pass = ob is None or ob <= thr.order_bias_pp
        malformed_pass = malformed_rate < thr.malformed_max
        verdict = "calibrated" if (agg_pass and order_pass and malformed_pass) else "not-calibrated"

    criterion_details: dict[str, Any] = {
        "agreement_min": thr.agreement_min,
        "kappa_min": thr.kappa_min,
        "order_bias_pp": thr.order_bias_pp,
        "malformed_max": thr.malformed_max,
        "pass_threshold": thr.pass_threshold,
        "n_scored": n,
        "agg_criterion": "agreement >= min OR kappa >= min",
    }
    if n:
        criterion_details["agg_met"] = agreement >= thr.agreement_min or kappa >= thr.kappa_min
        criterion_details["order_met"] = ob is None or ob <= thr.order_bias_pp
        criterion_details["malformed_met"] = malformed_rate < thr.malformed_max

    return CalibrationReport(
        judge_id=judge.judge_id,
        dimension=gold_entries[0].dimension if gold_entries else "",
        kind=_judge_kind(judge),
        n_entries=n,
        agreement=agreement,
        weighted_kappa=kappa,
        fp=fpos,
        fn=fneg,
        fp_rate=(fpos / n) if n else 0.0,
        fn_rate=(fneg / n) if n else 0.0,
        order_bias_pp=ob,
        verbosity_bias=verbosity_bias,
        self_preference=None,
        repeat_consistency=repeat_consistency,
        repeat_samples=repeat_n,
        malformed_rate=malformed_rate,
        total_judge_calls=total_calls,
        verdict=verdict,
        criterion_details=criterion_details,
        raw_scores=raw,
    )


def _human_level(rubric: JudgeRubric | None, human_score: float) -> int:
    if rubric is not None and rubric.scale:
        return rubric.categorize(human_score)[0]
    return 1 if human_score >= 0.5 else 0


def _malformed_rate(judge: Judge) -> float:
    fn = getattr(judge, "malformed_rate", None)
    if callable(fn):
        return float(fn())
    return 0.0


def _call_count(judge: Judge) -> int:
    return int(getattr(judge, "call_count", 0))


def _judge_kind(judge: Judge) -> str:
    if isinstance(judge, OfflineJudge):
        return "offline/mock"
    if isinstance(judge, LLMJudge):
        return "llm"
    return getattr(judge, "judge_id", "unknown")

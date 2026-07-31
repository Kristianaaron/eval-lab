"""Unit tests for the Phase 4 judge subsystem (spec 14)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from eval_lab.adapters.mock import MockModelAdapter
from eval_lab.judges.adapter import LLMJudge, OfflineJudge, build_judge
from eval_lab.judges.calibration import (
    GoldEntry,
    exact_agreement,
    run_calibration,
    weighted_kappa,
)
from eval_lab.judges.pairwise import comparable, order, order_bias_pp
from eval_lab.judges.protocol import (
    JudgeConfig,
    JudgementScale,
    JudgeResult,
    JudgeRubric,
    parse_judge_json,
)

SCALE = [
    JudgementScale(level=4, label="correct", min=0.8),
    JudgementScale(level=3, label="mostly_correct", min=0.55),
    JudgementScale(level=2, label="incomplete", min=0.3),
    JudgementScale(level=1, label="wrong", min=0.0),
]
RUBRIC = JudgeRubric(description="d", scale=SCALE)


class FakeJudge:
    """Deterministic judge returning a fixed score per output."""

    judge_id = "fake"

    def __init__(self, scores: dict[str, float]) -> None:
        self._scores = scores
        self.call_count = 0
        self.malformed_count = 0
        self.config = SimpleNamespace(rubric=RUBRIC)

    def judge(
        self,
        *,
        task_instruction=None,
        rubric="",
        output="",
        dimension=None,
        run_dir=None,
        identity=None,
    ) -> JudgeResult:
        self.call_count += 1
        s = self._scores.get(output, 0.5)
        level, label = RUBRIC.categorize(s)
        return JudgeResult(
            dimension=dimension or "answer_quality",
            score=s,
            label=label,
            label_level=level,
        )

    def malformed_rate(self) -> float:
        return 0.0


def _entry(output: str, human_score: float, human_label: str = "") -> GoldEntry:
    return GoldEntry(
        task_instruction="Compute 17*23.",
        rubric="d",
        output=output,
        dimension="answer_quality",
        human_label=human_label or "x",
        human_score=human_score,
    )


# ---------------------------------------------------------------------------
# strict structured output validation
# ---------------------------------------------------------------------------


def test_parse_judge_json_valid():
    payload = (
        '{"dimension": "answer_quality", "score": 0.9, "label_level": 4, '
        '"label": "correct", "rational": "ok"}'
    )
    em = parse_judge_json(payload)
    assert em.score == 0.9 and em.label_level == 4 and em.dimension == "answer_quality"


def test_parse_judge_json_rejects_malformed():
    with pytest.raises(ValueError):
        parse_judge_json("not json")
    with pytest.raises(ValueError):
        parse_judge_json("{}")  # missing required fields
    bad_score = '{"dimension": "x", "score": 5.0, "label_level": 1, "label": "y"}'
    with pytest.raises(ValueError):
        parse_judge_json(bad_score)  # score out of range
    bad_key = '{"dimension": "x", "score": 0.5, "label_level": 1, "label": "y", "unknown": 1}'
    with pytest.raises(ValueError):
        parse_judge_json(bad_key)  # extra key


def test_malformed_output_counted_not_accepted():
    cfg = JudgeConfig(
        id="j",
        dimension="answer_quality",
        kind="llm",
        rubric=RUBRIC,
        model={"id": "m", "provider_type": "mock", "model_name": "mock"},
    )
    judge = LLMJudge(MockModelAdapter(), cfg)
    # Mock structured stub output does not validate (score/label_level are strings) => malformed.
    r = judge.judge(task_instruction="t", rubric="d", output="x", dimension="answer_quality")
    assert r.error is not None and r.label == "malformed"
    assert judge.malformed_count == 1
    assert judge.malformed_rate() == 1.0


def test_build_judge_offline_returns_mock():
    cfg = JudgeConfig(id="a", dimension="answer_quality", kind="llm", rubric=RUBRIC)
    j = build_judge(cfg, offline=True)
    assert isinstance(j, OfflineJudge)
    assert j.judge_id == "a"


def test_build_judge_llm_without_model_raises():
    cfg = JudgeConfig(id="a", dimension="answer_quality", kind="llm", rubric=RUBRIC)
    with pytest.raises(ValueError):
        build_judge(cfg)


# ---------------------------------------------------------------------------
# agreement / kappa math (hand-computed)
# ---------------------------------------------------------------------------


def test_exact_agreement_and_kappa_perfect():
    pred = [0, 0, 1, 2, 2]
    human = [0, 0, 1, 2, 2]
    assert exact_agreement(pred, human) == 1.0
    assert weighted_kappa(pred, human) == 1.0


def test_weighted_kappa_hand_computed_zero():
    # levels {0,1}: matrix[0][0]=3, [0][1]=2 -> po=0.6, pe=0.6, kappa=0
    assert pytest.approx(weighted_kappa([0, 0, 0, 0, 0], [0, 1, 0, 1, 0])) == 0.0


def test_weighted_kappa_hand_computed():
    # levels {0,1,2}: k=3, predictions [0,1] humans [0,2] -> kappa = 0.5
    assert pytest.approx(weighted_kappa([0, 1], [0, 2]), abs=1e-9) == 0.5


def test_agreement_and_kappa_non_trivial():
    pred = [4, 1, 4, 2]
    human = [4, 1, 4, 3]
    assert pytest.approx(exact_agreement(pred, human)) == 0.75
    # Hand-computed linear-weighted kappa for the above = 0.870967...
    assert pytest.approx(weighted_kappa(pred, human), abs=1e-4) == 9 / 11


# ---------------------------------------------------------------------------
# full calibration run with hand-computed fp/fn/agreement
# ---------------------------------------------------------------------------


def test_run_calibration_metrics_hand_computed():
    entries = [
        _entry("o1", 0.9),
        _entry("o2", 0.2),
        _entry("o3", 0.85),
        _entry("o4", 0.6),
    ]
    judge = FakeJudge({"o1": 0.8, "o2": 0.1, "o3": 0.9, "o4": 0.3})
    rep = run_calibration(judge, entries, repeat_samples=0)
    assert rep.n_entries == 4
    assert pytest.approx(rep.agreement, abs=1e-9) == 0.75
    assert pytest.approx(rep.weighted_kappa, abs=1e-4) == 9 / 11
    assert rep.fp == 0 and rep.fn == 1
    assert rep.fp_rate == 0.0
    assert rep.fn_rate == 0.25


def test_run_calibration_dimension_unscored():
    judge = FakeJudge({})
    rep = run_calibration(judge, [], repeat_samples=0)
    assert rep.verdict == "dimension-unscored"


# ---------------------------------------------------------------------------
# pairwise randomization
# ---------------------------------------------------------------------------


def test_pairwise_order_deterministic():
    assert order(42, "A", "B") == order(42, "A", "B")
    first = order(42, "A", "B")
    assert set(first) == {"A", "B"}  # always a permutation of both


def test_pairwise_order_both_orders_occur_over_seeds():
    pairs = {order(s, "A", "B") for s in range(64)}
    assert ("A", "B") in pairs and ("B", "A") in pairs


def test_self_preference_guard():
    assert comparable("m1", "m2")
    assert not comparable("m1", "m1")
    assert not comparable(None, None)


def test_order_bias_pp():
    assert order_bias_pp([]) is None
    j = [
        {"first_preference": 1, "second_preference": 1},
        {"first_preference": 2, "second_preference": 1},
    ]
    assert order_bias_pp(j) == 50.0
    j2 = [
        {"first_preference": 1, "second_preference": 1},
        {"first_preference": 2, "second_preference": 2},
        {"first_preference": 0, "second_preference": 0},
    ]
    assert order_bias_pp(j2) == 0.0

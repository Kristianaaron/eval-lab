"""Unit tests for the Phase 5 analysis layer (comparison, slices, pareto, etc.)."""

from __future__ import annotations

from math import isfinite

import pytest

from eval_lab.analysis import (
    Point,
    RunRow,
    aggregate_suite,
    bootstrap_ci,
    build_task_rows,
    compare_groups,
    detect_regressions,
    is_significant,
    mean,
    median,
    paired_confidence_interval,
    pareto_frontier,
    quantile,
    slice_tasks,
    weighted_mean,
)
from eval_lab.analysis.significance import paired_deltas, win_tie_loss
from eval_lab.analysis.weighting import load_weighting_scenario, reweight_tasks


def make_row(
    task: str,
    model: str,
    score: float | None,
    passed: bool | None,
    duration: float | None = None,
    *,
    domain: list[str] | None = None,
) -> RunRow:
    labels = {"domain": frozenset(domain or [])}
    return RunRow(
        run_id=f"{model}-{task}",
        task_id=task,
        task_version=1,
        model_id=model,
        suite_id=None,
        task_level="model",
        seed=None,
        score=score,
        passed=passed,
        duration_s=duration,
        labels=labels,
    )


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------


def test_mean_median_quantile_empty() -> None:
    assert mean([]) == 0.0
    assert median([]) == 0.0
    assert quantile([], 0.5) == 0.0


def test_statistics_known_values() -> None:
    assert mean([1, 2, 3, 4]) == 2.5
    assert median([1, 2, 3, 4]) == 2.5
    assert median([1, 2, 3]) == 2
    assert quantile([1, 2, 3, 4], 0.5) == 2.5
    assert weighted_mean([1, 2], [1, 3]) == 1.75


def test_bootstrap_ci_deterministic_and_contains_mean() -> None:
    data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    a = bootstrap_ci(data, seed=42)
    b = bootstrap_ci(data, seed=42)
    assert a == b  # seeded -> reproducible
    low, high = a
    assert low <= mean(data) <= high
    assert low < high


def test_bootstrap_ci_empty_nan() -> None:
    low, high = bootstrap_ci([])
    assert not isfinite(low) and not isfinite(high)


# ---------------------------------------------------------------------------
# significance
# ---------------------------------------------------------------------------


def test_paired_deltas_and_win_tie_loss() -> None:
    base = [1.0, 0.5, 0.0, 1.0]
    cand = [1.0, 0.0, 0.8, 1.0]
    assert paired_deltas(base, cand) == [0.0, -0.5, 0.8, 0.0]
    wins, ties, losses = win_tie_loss(base, cand)
    assert (wins, ties, losses) == (1, 2, 1)


def test_ci_and_significance_small_sample() -> None:
    base = [1.0, 1.0, 1.0]
    cand = [0.9, 0.9, 0.9]
    ci = paired_confidence_interval(base, cand)
    assert ci[0] is not None and ci[1] is not None
    # Wide/tiny-sample comparisons must not claim significance.
    assert is_significant(ci, sample_size=3, min_samples=5) is False
    # With enough samples it can become significant.
    assert is_significant((0.1, 0.5), sample_size=10) is True
    assert is_significant((-0.5, 0.1), sample_size=10) is False


# ---------------------------------------------------------------------------
# regression
# ---------------------------------------------------------------------------


def test_detect_regressions() -> None:
    regs = detect_regressions(["a", "b", "c"], [1.0, 0.8, 0.5], [0.4, 0.9, 0.9], threshold=0.2)
    by_id = {r.task_id: r for r in regs}
    assert by_id["a"].regressed is True
    assert by_id["b"].regressed is False
    assert by_id["c"].improved is True


# ---------------------------------------------------------------------------
# pareto
# ---------------------------------------------------------------------------


def test_pareto_frontier() -> None:
    points = [
        Point("high", 0.9, 5.0),
        Point("fast", 0.4, 0.5),
        Point("middle", 0.7, 2.0),
        Point("dominated", 0.5, 3.0),
    ]
    frontier = pareto_frontier(points)
    labels = {p.label for p in frontier}
    assert "high" in labels
    assert "fast" in labels
    assert "middle" in labels
    # 'dominated' is worse on quality and latency than 'middle'.
    assert "dominated" not in labels


def test_pareto_memory_dimension() -> None:
    a = Point("a", 0.8, 1.0, memory=10)
    b = Point("b", 0.8, 1.0, memory=20)
    frontier = pareto_frontier([a, b])
    assert [p.label for p in frontier] == ["a"]


# ---------------------------------------------------------------------------
# weighted suites and slicing
# ---------------------------------------------------------------------------


def test_aggregate_suite_weighted_and_unweighted() -> None:
    runs = [
        make_row("t1", "A", 1.0, True, domain=["coding"]),
        make_row("t2", "A", 0.5, False, domain=["mathematics"]),
        make_row("t3", "A", 0.8, True, domain=["coding"]),
    ]
    weights = {"t1": 1.0, "t2": 1.0, "t3": 2.0}
    agg = aggregate_suite(runs, weights)
    assert agg.task_count == 3
    assert agg.scored_tasks == 3
    # weighted = (1*1 + 1*0.5 + 2*0.8)/4 = 0.775
    assert agg.weighted_score == pytest.approx(0.775)
    # unweighted = (1 + 0.5 + 0.8)/3
    assert agg.unweighted_score == pytest.approx((1 + 0.5 + 0.8) / 3)


def test_build_task_rows_merges_repetitions() -> None:
    runs = [
        make_row("t1", "A", 1.0, True),
        make_row("t1", "A", 0.0, False),  # second repetition fails
    ]
    rows = build_task_rows(runs)
    assert len(rows) == 1
    assert rows[0].score == 0.5
    assert rows[0].n_runs == 2
    assert rows[0].passed is False  # all-pass definition


def test_slice_tasks_multi_label() -> None:
    rows = build_task_rows(
        [
            make_row("t1", "A", 1.0, True, domain=["coding"]),
            make_row("t2", "A", 0.4, False, domain=["mathematics"]),
            make_row("t3", "A", 0.8, True, domain=["coding"]),
        ]
    )
    slices = slice_tasks(rows, "domain")
    assert set(slices) == {"coding", "mathematics"}
    assert slices["mathematics"].task_count == 1
    assert slices["coding"].task_count == 2
    assert slices["coding"].unweighted_score == pytest.approx(0.9)


def test_weighting_scenario_reweights() -> None:
    sc = load_weighting_scenario("configs/reports/daily_driver_weighted.yaml")
    assert sc.domain_weights["coding"] == 25
    rows = build_task_rows(
        [make_row("t1", "A", 1.0, True, domain=["coding"]), make_row("t2", "A", 0.0, False)]
    )
    rw = reweight_tasks(rows, sc)
    assert rw[0].weight == pytest.approx(25.0)  # coding scaled by 25
    assert rw[1].weight == 1.0  # no domain -> unchanged


# ---------------------------------------------------------------------------
# paired comparison engine
# ---------------------------------------------------------------------------


def test_compare_groups_detects_regressions() -> None:
    base = [
        make_row("t1", "B", 1.0, True),
        make_row("t2", "B", 0.8, True),
        make_row("t3", "B", 0.9, True),
    ]
    cand = [
        make_row("t1", "C", 1.0, True),
        make_row("t2", "C", 0.2, False),
        make_row("t3", "C", 0.3, False),
    ]
    cmp = compare_groups(base, cand, base_label="B", candidate_label="C", regress_threshold=0.2)
    assert cmp.sample_size == 3
    assert set(cmp.matched_task_ids) == {"t1", "t2", "t3"}
    assert [r.task_id for r in cmp.regressions] == ["t2", "t3"]
    assert cmp.failure_transitions["pass_to_fail"] == 2
    assert cmp.wins + cmp.ties + cmp.losses == 3
    assert cmp.losses == 2


def test_compare_groups_identical_no_false_regression() -> None:
    runs = [make_row(t, "M", 0.9, True) for t in ("t1", "t2", "t3")]
    cmp = compare_groups(runs, runs, base_label="M", candidate_label="M", regress_threshold=0.05)
    assert cmp.regressions == ()
    assert (cmp.wins, cmp.ties, cmp.losses) == (0, 3, 0)
    assert cmp.mean_delta == 0.0


def test_compare_groups_ignores_unmatched_tasks() -> None:
    base = [make_row("t1", "B", 1.0, True), make_row("only_base", "B", 1.0, True)]
    cand = [make_row("t1", "C", 0.5, True), make_row("only_cand", "C", 1.0, True)]
    cmp = compare_groups(base, cand)
    assert cmp.matched_task_ids == ["t1"]

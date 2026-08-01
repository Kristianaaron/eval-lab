# Phase 5 Report — Suite & Comparison Engine

**Status:** complete · **Version:** 0.8.0 · **Date:** 2026-08-01

## Deliverables (spec §23 Phase 5)

| Deliverable | Where |
|---|---|
| Weighted suites | `src/eval_lab/analysis/weighted.py` — `aggregate_suite` / `aggregate_task_rows`, composite recomputed from suite weights; raw unweighted aggregates always reported beside weighted |
| Alternative weighting scenarios | `src/eval_lab/analysis/weighting.py` + `configs/reports/{baseline,daily_driver_weighted}.yaml` (spec 8.1B suggested domain allocations); re-composite via `--scenario` |
| Label slicing | `src/eval_lab/analysis/slices.py` — slice by domain/capability/modality/trajectory_stage/failure_mode/difficulty, weighted + unweighted |
| Paired comparisons | `src/eval_lab/analysis/comparison.py` — `compare_groups` pairs base vs candidate on shared tasks |
| Bootstrap intervals | `src/eval_lab/analysis/statistics.py` + `significance.py` — seeded percentile CI, win/tie/loss, significance gated on sample size |
| Regression reports | `src/eval_lab/analysis/regression.py` + `reports/analysis.py` — per-task delta list, failure transitions, resource deltas |
| Pareto analysis | `src/eval_lab/analysis/pareto.py` — quality vs latency/memory frontier |

Run rows are a pure, immutable `RunRow` (`analysis/rows.py`), loaded from the
SQLite index plus run manifests (duration), with task labels resolved from the
catalogue. All analysis functions are unit-testable without the pipeline.

## CLI (spec §19)

- `eval-lab evaluate <suite> --model <id> [--scenario yaml] [--json]` — weighted suite aggregate + label slices, recomputed from config; writes `reports/suite_<suite>_<model>.md`.
- `eval-lab compare <a> <b> [--threshold] [--json]` — a/b are model ids (all runs) or single run ids; paired comparison on shared tasks; writes `reports/compare_<a>_vs_<b>.md`. Candidate-minus-base deltas.
- `eval-lab pareto [--json]` — quality (mean aggregate) vs latency (mean duration) frontier across model configs.

## Exit gate verification

- **Two model configurations compared on identical tasks** — `compare mock-a mock-b` on a shared 3-task suite: `sample_size=3`, seeded bootstrap CI, win/tie/loss, no false regressions on deterministic output. Unit/`integration/test_phase5.py` prove regression detection flips when the candidate is meaningfully worse.
- **Reports identify meaningful regressions** — `detect_regressions` / `compare_groups.regressions` flag tasks beyond a configurable threshold; verified in `test_analysis.py` and `test_phase5.py`.
- **Composite recomputed from config** — `weighted_score` derives from suite per-task weights (and optional scenario domain weights); `test_evaluate_weighted_suite` asserts it end to end; raw unweighted shown always (spec 8.1B).

## Why Phase 5 was skipped earlier

The planning question the user re-raised ("why was that phase skipped?"). The
repo does not contain a recorded rationale; what follows is the observable
history plus the working explanation.

Evidence from the commit log: Phase 6 (the 36-task catalogue) was committed
*before* Phase 5 — commit `b3d79b9` bundles "Phase 4 … ; Phase 6: 36-task
catalogue" — and Phase 5's comparison engine (`analysis/`) was simply never
built before the dashboard landed. So it was **skipped out of order**, not
blocked: nothing technical prevented it (no prior `analysis/` package, no
weighted-suite/compare/pareto code existed).

[INFERENCE] The most likely reason it was deprioritized: the task catalogue
(Phase 6) is a prerequisite for the daily-driver/general-retention/stress
suites that Phase 5 aggregates, and the dashboard was the more visible
deliverable — so the largest, least visible core-engine slice (weighted
aggregation + comparison statistics) was left open until now. It is now
implemented and its exit gates pass.

## Tests & hygiene

- New: 16 unit tests (`tests/unit/test_analysis.py`) + 3 integration tests (`tests/integration/test_phase5.py`) + 1 dashboard `/api/models` test.
- Full suite: **121 passed**. `ruff check`, `ruff format --check`, `mypy src` all clean.
- Reports are written to `reports/` (gitignored generated output).

## Also in this change (dashboard)

- `/api/models` endpoint + Svelte model selector showing active models and run
  times (median/mean/min/max duration, run count) on the Runs filter and
  Overview card — requested before Phase 5 work began.

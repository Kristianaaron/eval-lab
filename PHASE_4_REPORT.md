# PHASE_4_REPORT — advanced scorers, LLM judges, gold-set calibration

**Status:** COMPLETE
**Date:** 2026-08-01
**Host:** eval-node (Linux aarch64)
**Scope:** Phase 4 only (spec §13.2/13.3, §14). Advanced scorers, the judge
subsystem (LLM + offline mock), gold-set calibration, pairwise order
randomization, and the calibration report.

---

## 1. What was built

| Deliverable | Location |
|-------------|----------|
| `unit_test` scorer | `src/eval_lab/scorers/unit_test.py` |
| `artifact` scorer | `src/eval_lab/scorers/artifact.py` |
| `trajectory` scorer | `src/eval_lab/scorers/trajectory.py` |
| `visual` scorer | `src/eval_lab/scorers/visual.py` |
| Scorer registry package | `src/eval_lab/scorers/__init__.py` (side-effect registration) |
| Judge protocol + config schema | `src/eval_lab/judges/protocol.py` |
| LLM + offline-judge adapters | `src/eval_lab/judges/adapter.py` |
| Pairwise order randomization | `src/eval_lab/judges/pairwise.py` |
| Calibration math + report | `src/eval_lab/judges/calibration.py` |
| CLI `calibrate-judge` | `src/eval_lab/cli/main.py` |
| Example judge YAMLs | `configs/judges/answer_quality.yaml`, `configs/judges/pairwise.yaml` |
| Human-labeled gold set | `gold/judge_calibration/answer_quality.json` |
| Unit tests | `tests/unit/test_scorers_advanced.py`, `tests/unit/test_judges.py` |
| Integration tests | `tests/integration/test_phase4.py` |

## 2. Files created / modified

- **New** `src/eval_lab/scorers/{unit_test,artifact,trajectory,visual}.py` and
  `src/eval_lab/scorers/__init__.py`.
- **New** `src/eval_lab/judges/{__init__,protocol,adapter,pairwise,calibration}.py`.
- **Modified** `src/eval_lab/cli/main.py` (added `calibrate-judge`).
- **New** `configs/judges/*.yaml`, `gold/judge_calibration/answer_quality.json`.
- **New** `tests/unit/test_scorers_advanced.py`, `tests/unit/test_judges.py`,
  `tests/integration/test_phase4.py`.
- **Modified** `CHANGELOG.md`.

## 3. Scorer ids + configs

Registered via `register_scorer` (imported by `scorers/__init__.py`), so
`available_scorers()` includes `unit_test`, `artifact`, `trajectory`, `visual`
plus the existing `exact`, `regex`, `json_schema`.

| id | config | 1.0/passed | error (never silent zero) |
|----|--------|-----------|---------------------------|
| `unit_test` | `command` (req), `workspace` (default run_dir/cwd), `timeout_seconds` (60) | exit code 0; details `exit_code`, `stdout_head`, `stderr_head` (≤2000), `duration_s`, `command` | process fails to *launch* (e.g. bad workspace) |
| `artifact` | `path` (rel run_dir), `hash` (sha256), `min_size` | exists + all checks; missing/mismatch = legit 0.0 | cannot resolve a workspace |
| `trajectory` | `weights` {dim→w}, `pass_threshold` (0.6) | composite weighted mean of *scored* dims ≥ threshold; no-evidence dims excluded, recorded in `scored_dimensions`/`skipped_dimensions` | no trace / unparsable / no evidence at all |
| `visual` | `mode` `json_scene`/`image`, geometry `expected`, `reference*(s)`, `method` `exact`/`diff`, `pass_threshold`, `required` | all enabled checks (0..1); missing ref/produced = error unless `required:false` then legit 0.0 | missing ref/produced/scene, invalid scene, unknown method (when required) |

`trajectory` dimension proxies (reasoned strictly from actual `tool_result` /
`model_completion` / `agent_turn_start` events):
`tool_selection` = ok/total; `repeats_failed_action` = 1 − repeats/failures;
`recovery` = recoveries/failures; `verification` = verified-writes/writes;
`plan_to_action` = reasoned-before-acting proxy; `unnecessary_actions` =
1 − redundant/total; `destructive_actions` = 1 − shell-fraction.

## 4. Judge subsystem (spec 14)

- **protocol.py** — `Judge` protocol; strictly validated structured output
  (`JudgeEmission`, `extra="forbid"`; `parse_judge_json` rejects invalid JSON,
  missing/out-of-range/unknown fields). `JudgeConfig`, rubric scale, and
  calibration thresholds.
- **adapter.py** — `LLMJudge` wraps a `ModelAdapter` (reuse of
  `adapters/base` + `build_adapter`; local endpoints supported). Prompt per
  14.2: task instruction, anchored rubric, output, deterministic validator
  results, **no model identity**. Malformed responses are counted
  (`malformed_count`, `malformed_rate`) and returned as an error result, never
  silently accepted. `OfflineJudge` is a deterministic, clearly-marked mock
  (verbosity/keyword heuristic) for endpoint-free runs. `build_judge` returns
  the mock when `kind` is `mock`/`offline` or `--offline` is passed.
- **pairwise.py** — pure `order(seed, a, b) -> (first, second)` (seeded,
  deterministic, recorded), `comparable(a_identity, b_identity)` self-preference
  guard, `order_bias_pp(judgements)`.
- **calibration.py** — `load_gold_set`, `load_judge_config`, `run_calibration`,
  `write_calibration_report`. Computes exact agreement, linear-weighted
  Cohen's kappa (`weighted_kappa`), FP/FN rates, order bias, verbosity bias,
  repeat consistency, self-preference (reported n/a without identity-tagged
  pairwise gold), and malformed-output rate.

## 5. Judge threshold defaults (config `thresholds`)

- `agreement_min: 0.75`, `kappa_min: 0.60` — **weighted agreement criterion**:
  calibrated iff `agreement >= 0.75 OR weighted_kappa >= 0.60`.
- `order_bias_pp: 5.0` — pairwise order bias must be ≤ 5 percentage points.
- `malformed_max: 0.01` — malformed-output rate must be < 1%.
- `pass_threshold: 0.5` — used for FP/FN pass classification.
- Verdict: `calibrated` | `not-calibrated` | `dimension-unscored`.

## 6. Offline smoke result

```bash
.venv/bin/python -m eval_lab.cli.main calibrate-judge answer_quality --offline
# VERDICT: not-calibrated
# report: reports/calibration_answer_quality_answer_quality.md  (.md + .json)
```

The mock judge is deliberately verbosity-biased, so it reports
`exact agreement 0.200`, `weighted kappa -0.400`, `verbosity bias 0.927`,
`malformed 0%` → **not-calibrated** (a truthful, endpoint-free demonstration;
an LLM judge configured in `configs/judges/*.yaml` would be evaluated against
the same gold set and thresholds).

## 7. Acceptance / verification

- `.venv/bin/python -c 'import eval_lab.scorers.unit_test, eval_lab.scorers.artifact, eval_lab.scorers.trajectory, eval_lab.scorers.visual, eval_lab.judges.calibration'` succeeds.
- `available_scorers()` includes `unit_test`, `artifact`, `trajectory`, `visual`.
- Offline `calibrate-judge` against the mock produces a markdown calibration
  report with a verdict line (verified above).
- 44 new tests pass; `mypy src` clean (51 files); `ruff check` + `ruff format
  --check` clean for the new/modified paths.

## 8. Assumptions

- `trajectory` uses *documented proxies* because trace `tool_result` payloads
  do not carry tool arguments; each dimension's heuristic and evidence
  requirement is spelled out in `trajectory.py` and the report.
- `visual:image` "normalized pixel diff" is implemented as a deterministic
  normalized **byte** diff since the repo has no image library dependency.
- The gold set covers the requested `answer_quality` categories
  (strong / mediocre / subtly-wrong / verbose-but-wrong / concise-correct);
  pairwise order-bias is reported `n/a` when no pairwise gold is present and
  is not counted as a failure in that case.
- 2 pre-existing `test_phase0.py` failures referencing the old flat
  `tasks/mathematics/basic_addition.yaml` path are due to the parallel Phase 6
  task-catalogue restructuring (`tasks/<cat>/<slug>/task.yaml`), not this
  change.

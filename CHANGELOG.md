# Changelog

All notable changes to eval-lab are documented here. Format: Keep a Changelog.

## [0.5.0] - 2026-08-01

Phase 4: advanced scorers + LLM judge calibration.

- Advanced scorers (spec 13.3): `unit_test`, `artifact`, `trajectory`, `visual`
  registered in the scorer registry. Errored scorers are excluded by
  `aggregate()` and never silently zeroed.
- Judge subsystem (spec 14): strict structured-output protocol, `LLMJudge`
  over any `ModelAdapter` (local endpoints supported), a deterministic offline
  mock judge, and seeded pairwise A/B ordering with self-preference guards.
- Calibration (spec 14.3) against a human gold set: exact agreement, weighted
  Cohen's kappa, FP/FN rates, order bias, verbosity bias, repeat consistency,
  malformed-output rate, and a calibrated verdict, exported as markdown + JSON.
- CLI `calibrate-judge <judge-id>` with `--offline` mock path.
- Example judge YAMLs (`configs/judges/`) and a human-labeled gold set
  (`gold/judge_calibration/`).
- Tests: 44 new unit/integration tests covering scorer pass/fail/error paths,
  calibration math, malformed-rate counting, and pairwise determinism.

## [0.6.0] - 2026-08-01

Phase 6: target-workload task catalogue (spec 9).

- Grew the catalogue from 6 to 38 deterministically-scored tasks across coding (8),
  frontend/visual (6), voxel/spatial (6), agentic (4) + tool-calling (4), reasoning/math (4+),
  and long-context/research (4), plus retained general/hardware tasks.
- Every task is a self-contained package (`tasks/<category>/<slug>/` with `task.yaml`,
  `prompt.md` and committed fixtures), with valid controlled-vocabulary labels and
  deterministic oracles (exact/regex/json_schema/unit_test/artifact).
- Suite families (spec 8.1): `daily-driver`, `general-retention`, `stress`, `atlas`
  (`configs/suites/*.yaml`), each referencing existing task ids.
- Provenance/leakage documented in `PHASE_6_REPORT.md`: zero test tasks reused as
  training or calibration data; fixtures original, self-contained, no network at eval time.
- Tasks consolidated to the canonical package layout; tests updated to the new paths.

## [0.4.0] - 2026-07-31

Phase 3: telemetry and performance.

- Telemetry package (spec 15): system, process, NVMe, network and NVIDIA
  collectors reading from `/proc` and `/sys`; missing metrics reported as
  `available: false` rather than fabricated.
- `TelemetrySampler` samples on a configurable interval as a bounded-overhead
  daemon thread and emits `resource_sample` trace events through
  `TraceRecorder` (monotonic sequence numbers per spec 6.5).
- Cold/warm `telemetry_marker` events recorded at run start by the direct,
  agent and perf runners; `warm_state` persisted on the manifest.
- Streaming timing protocol: `GenerationTiming` + `StreamingModelAdapter` and
  a deterministic `TimedMockAdapter` that streams tokens with per-token
  wall-clock timestamps.
- `PerfRunner` executes tasks under telemetry and streaming timing; TTFT and
  decode throughput are recomputed from raw trace timestamps and checked
  against the adapter's report (`telemetry_correlation` event).
- Per-node telemetry correlation (`telemetry/correlation.py`) aggregates
  `resource_sample` events by node id; node attribution on every sample.
- `RunManifest` gains `telemetry_stream` and `timing` (spec 6.4).
- Hardware-performance suite (`configs/suites/hardware_perf.yaml`), a
  `hardware` domain label, and `tasks/hardware/perf_probe.yaml`.
- CLI `perf` command runs the hardware suite end to end.
- Tests: 13 telemetry unit tests, 4 Phase 3 integration tests.

## [0.3.0] - 2026-07-31

Phase 2: agent execution.

- Sandbox abstraction with local-process and Docker backends, workspace
  hashing and escape safety.
- Filesystem and shell tools over a typed tool protocol; deterministic
  scripted tool-calling adapter.
- `AgentRunner` agent loop with budgets, timeouts and trajectory tracing;
  validators run after workspace freeze.

## [0.2.0] - 2026-07-31

Phase 1: direct evaluation core.

- Task loader/validator with fixture-reference checks and task registry index.
- Direct runner, OpenAI-compatible and scripted adapters.
- Exact/regex/json/rubric-free deterministic scorers.
- JSON/JSONL + SQLite persistence and Markdown run reports.

## [0.1.0] - 2026-07-31

Phase 0 scaffold:

- Versioned Pydantic schemas: TaskSpec, SuiteSpec, ModelConfig, HarnessConfig,
  RunManifest, ScoreResult, TraceEvent.
- Controlled label registry with validation and aliases.
- YAML task/suite loader with fixture-reference checks.
- CLI: `doctor`, `validate task|suite`, `list tasks` (JSON output, exit codes).
- Deterministic mock model adapter.
- Packaging (uv/hatchling), Ruff, mypy, pytest.
- Docs: architecture, data-contracts, ADR-0001.

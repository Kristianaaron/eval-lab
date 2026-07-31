# Changelog

All notable changes to eval-lab are documented here. Format: Keep a Changelog.

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

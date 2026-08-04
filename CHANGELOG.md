# Changelog

All notable changes to eval-lab are documented here. Format: Keep a Changelog.

## [0.17.0] - 2026-08-04

Milestone 3: Atlas Lab — a genuine lightweight layerwise MoE tracer (handoff
option A; resolves the pending fork). Real CPU router/expert forward pass over
deterministic calibration contexts measures actual per-layer/per-expert
saliency — no fabricated numbers.

- **Tracer core** (`atlas/`): `model.py` (fixed-seed synthetic mini-MoE with
  meaningful expert geometry, materialized `config.json` + `weights.json`),
  `tracer.py` (`CalibrationPool` with capability-labelled contexts; `trace_layer`
  emits per-expert activation frequency, mean gate probability, output-norm
  variance, and per-label breakdowns), `plans.py` (keep-budget prune topologies
  derived only from measured saliency), `store.py` (`AtlasRunStore` writing the
  atlas-bridge-compatible `atlas_out/atlas_runs/<id>/` artifacts + recovery
  checkpoint).
- **Runtime service** (`services/atlas_runtime.py`): M3 runs as a restart-safe
  `atlas` orchestrator job with per-layer progress, pause/resume at safe
  boundaries, cancel, checkpoint recovery, source-model linking (`atlas-traced`),
  and an honest resource estimator (one-layer probe calibrated).
- **Orchestrator**: `JobOrchestrator.pause/resume` (`running→pausing→paused`,
  `paused→resuming→running`) with shared job store across eval and atlas jobs.
- **API**: `/api/atlas/config`, `/api/atlas/estimate`, `/api/atlas-jobs` (+
  `/{id}` and `/{id}/{cancel,pause,resume}`), `/api/atlas-runs[/{id}]`.
- **GUI Atlas Lab**: build-atlas wizard (source/suite/depth/budgets +
  estimate + launch), live job monitor with Pause/Resume/Cancel and polling,
  completed-runs browse + deep-dive (plans, keep-maps, saliency).
- **Bug fix**: `JobStore.save` raced under concurrent worker/API saves (shared
  `.tmp` name → intermittent `FileNotFoundError`); now each save uses a unique
  temp name with atomic rename.
- Tests: 4 new; full suite 168 passed; ruff/mypy/format clean; SPA rebuilt.
  Report: `docs/gui-milestone-3.md`.

## [0.16.0] - 2026-08-04

Milestone 4: Explorer — one cross-registry browse over every recorded artifact.

- **Registries endpoint** (`GET /api/explorer/registries`): a single corpus
  summary across runs (total/pass/fail/avg), jobs (by kind/state), atlas runs,
  experiments, model assets, and suites — the browse surface never re-scatters.
- **Run detail extended**: `/api/runs/{id}` now also returns `report` (the run's
  markdown report) and `artifacts` (extra artifact files under `runs/<id>/artifacts/`)
  so the deep-dive shows identity + result + report + raw files, not just the index row.
- **GUI Explorer area**: new nav destination with a registries summary bar and
  sectioned browse (Runs / Atlas runs / Experiments / Model assets / Jobs / Suites)
  with facet filters, each row linking into its existing deep-dive or area.
- **Runs deep-dive** (`#/explorer/run/:id`): tabbed detail — Overview (manifest
  identity + scores), Result (output/error + markdown report), Telemetry (ECharts
  series over node samples), Trace (event log), and Raw (stored artifact listing +
  `manifest.json`/`result.json`/`report.md` verbatim).
- Wired the previously-orphaned run-browse + run-detail Svelte components into the
  Explorer area; removed the orphaned `Runs.svelte` list (folded into Explorer).
- Tests: 2 new integration tests (explorer registries, run detail report/artifacts);
  full suite 164 passed; ruff/mypy/format clean. SPA rebuilt.

## [0.15.0] - 2026-08-04

Evaluation page redesign: config-left + per-domain rows, and a config-load fix.

- **Fixed config never loading**: the Evaluation SPA threw `ReferenceError: chip is
  not defined` (`class:chip` is a Svelte class directive bound to a missing
  variable), which killed `onMount` so `/api/eval-config` never resolved — the
  page sat on "Loading configuration…". Rewrote the domain chip as
  `class="chip"` + `class:on={...}`.
- **Layout**: replaced the full-width panels (`.grid.cols-2` was never defined in
  `app.css`, so cards spanned the whole row) with a two-column `.eval-layout`
  (`340px` config left / fluid right), collapsing to one column on narrow widths.
- **Config panel (left)**: model, harness, repeat, cold start, and domain chips
  that add/remove a row on the right; `Run new eval (n domains)` launches.
- **Domain rows (right)**: empty state until a domain is chosen, then one **flat row
   per domain** separated by thin dividers showing Domain, Score, a lifecycle status
  badge (pending / queued / evaluating / done / failed / cancelled), a View link to
  the job once terminal, and a circular minus-icon remove button.
- **One eval job per domain** so each row has a real lifecycle; Score is the
  average of that job's run `manifest.aggregate_score`. Recent-jobs list retained
  under the config panel.
- Rebuilt the SPA bundle.

## [0.14.0] - 2026-08-04

Experiments (M5) + Atlas Lab keep-map/saliency surfacing.

- **Experiment backend** (`schemas/experiment.py`, `storage/experiments.py`,
  `services/experiments.py`): a saved experiment pins one candidate plan from
  an imported atlas run as a named, evaluable intervention strategy. Created
  from an imported run + plan, it records the keep-map scope (`kept_per_layer`,
  `total_kept`), optionally a memory target, and links the registered
  derivative asset + source asset while preserving source identity.
- **API**: `GET/POST /api/experiments`, `GET/DELETE /api/experiments/{id}`;
  `POST /api/experiments` validates the run/plan and 400s on an unknown plan,
  404s on a missing run.
- **Atlas Lab GUI** (`AtlasLab.svelte`): new Imported atlas runs section
  listing `atlas_runs/<id>/` exports with Import/Details, a per-run detail
  view (candidate plans, per-layer keep-map chips with source expert ids +
  saliency, and a saliency table), wired to the atlas-bridge API.
- **Experiments GUI** (`Experiments.svelte`): replaced the M5 placeholder with
  a real list, create-from-run/plan form, detail cards, and delete.
- `.gitignore`: treated `atlas_out/` and `experiments/` as runtime registries.
- Tests: 3 integration tests; full suite 162 passed; ruff/mypy/format clean.

## [0.13.0] - 2026-08-04

Atlas bridge consumer — eval-lab side of the model-atlas file-manifest bridge.

- `services/atlas_bridge.py`: `AtlasBridgeService` discovers/imports
  `atlas_runs/<id>/` exports produced by the model-atlas `export` command,
  validates them against the reserved atlas schemas, persists an idempotent
  import record, and registers any derivative checkpoint as a model asset
  (`derivative_checkpoint`, `parent_asset_id` + `source_atlas_run_id`).
- `storage/atlas_imports.py`: JSON import store keyed by run id.
- `schemas/atlas_bridge.py`: typed `AtlasBridgeImport` / `AtlasPlanImport`
  reusing `UnitKeepMap` / `UnitIdentity` / `EvidenceKind` so prune topologies
  stay auditable per unit.
- API: `GET /api/atlas-bridge/runs`, `POST /api/atlas-bridge/import`,
  `GET /api/atlas-bridge/runs/{run_id}`.
- eval-lab never imports `model_atlas` (one-way dependency preserved; files
  are hand-authored or produced by the sibling engine).
- Tests: 5 new; full suite 159 passed; ruff/mypy/format clean.

## [0.12.0] - 2026-08-04

Atlas head/expert dissection: unit identity, keep-maps, and a micro-suite.

- **Intervention vocab** (`config/labels.py`): added `attention_head_pruning`
  (aliases `head-dropout`/`head-prune`) so a head-level cut is a first-class,
  validated, sliceable label alongside the existing `expert_pruning`.
- **Unit identity** (`schemas/atlas.py`): generalized the trace/keep identity to
  `UnitIdentity` with an explicit `unit_kind` (`expert`|`head`), so a kept head
  in a derivative always traces to the source head by stable id (top-4 vs top-8
  never renumber into each other). `AtlasTraceField.unit` now carries it.
- **Keep-map shape**: per-layer `UnitKeepMap` + `KeepMapEntry` (kept flag, `top_k`,
  measured saliency, signal, rank) — the auditable, per-unit artifact of a prune
  topology that the GUI/reporting can surface to users.
- **Micro-suite** `configs/suites/heads.yaml` (`family: heads`): reuses existing
  tasks to benchmark pruned derivatives on the dissected axes a cut must not
  break — code correctness, exact tool-call handling, and hardware speed.
- **Comparison slice** (`ComparisonService.compare_variants`): builds the explicit
  paired A/B matrix across keep-map variants of one source (free full / top-8 /
  top-4), the arbitration step for choose-a-prune-topology.
- Tests: 5 new; full suite 154 passed, ruff/mypy/format clean.

## [0.11.0] - 2026-08-02

Overview landing page redesign matching the reference layout mockup (kept the harness's
established dark theme; the mockup informed layout only).

- Overview now opens with a small "Home landing page" label and two centered CTA cards:
  **Run eval** → `#/evaluation` and **Compare models** → `#/comparisons`, each with a leading
  lucide icon, bold JetBrains Mono title and muted description, bordered on the dark theme.
- Below the CTA row: a compact overview-stats bar (registered/runnable/source checkpoints,
  active/failed jobs, total runs) plus the existing Hardware/environment and Registered-models
  tables as stacked bottom cards (horizontal scroll on narrow widths).
- Dropped the now-superseded full-width "Run a new eval" run tile.

## [0.10.0] - 2026-08-01

Architecture corrections (validation report) + Milestone 2: evaluation launch & monitoring.

Corrections:
- **Job orchestrator** (`schemas/job.py`, `storage/jobs.py`, `services/orchestrator.py`):
  one persisted, restart-safe state machine for every long-running operation;
  background workers, real progress/stage, safe-boundary cancellation, and
  restore-on-restart (orphaned active jobs flagged `failed_recoverable`).
- **Task `data_partition`** (`atlas_calibration`/`development_evaluation`/
  `held_out_evaluation`/`unset`) + leakage guard (`services/leakage.py`)
  so calibration data is never silently reused as held-out evidence.
- **Reserved atlas schemas** (`schemas/atlas.py`): evidence levels, the
  measured/estimated/predicted/inferred/causally-tested distinction, and
  stable source↔derivative expert identity.
- **Typed services**: `EvaluationService` (launch/monitor/cancel), `ComparisonService`
  (wraps the Phase 5 analysis engine), `EnvironmentService`; GUI no longer
  hard-codes hardware facts (served via `/api/environment`).
- **API**: `/api/environment`, `/api/jobs` (+cancel), `/api/eval-config`,
  `/api/eval-jobs` (create/status/cancel), `/api/comparisons/{compare,slices,pareto}`.

Milestone 2 (exit gate: existing harness launched from GUI, auditable runs,
correct interrupted state):
- GUI **Evaluation** area: configuration wizard (model/suite/harness/repeat/
  cold), live job monitor with real task progress + stage, cancel-at-boundary,
  results page (per-run links), and leakage warning.
- GUI **Jobs** area lists every job with persistent state; Overview source hardware
  facts from the environment service and shows active/failed counts.
- Tests: +11 (job state machine, restore-on-restart, leakage, platform API);
  full suite 149 passed, ruff/mypy/format clean.

## [0.9.0] - 2026-08-01

Eval-harness GUI — Milestone 1: model assets, inspection, action eligibility.

- Typed model-asset schemas (`schemas/model_asset.py`): `ModelAssetRecord`,
  `CheckpointInspection`, `ActionEligibility`, `EnvBudget` + request/result DTOs.
- Typed application service layer (`services/models.py`): `ModelAssetService`
  and a pure `resolve_available_actions(asset, budget)` eligibility engine that
  keeps business rules out of view components (spec 3.4).
- Lightweight checkpoint inspection (`inspection/checkpoint.py`): reads
  config + SafeTensors headers only (no tensor payloads); detects
  type/architecture/layers/routed experts/top-k/quantization, sizes, params,
  resident estimate, atlas compatibility and runnability. Oversized source
  checkpoints (e.g. Kimi K3) are classified atlas-compatible but not directly
  evaluable — with an explanatory reason (spec 3.3/14.1).
- Persistent model-asset registry (`storage/model_assets.py`, JSON files under
  `models/`) surviving restarts; idempotent synthetic fixtures seeded on first
  start (K3 source, DeepSeek V4 Flash, Qwen 2B, a derivative) — no full-model
  loads in CI.
- API: `/api/models-assets` CRUD, `/{id}/actions`, `/inspect`, `/fixtures`.
  Model routes registered before the SPA mount so the catch-all no longer
  shadows them.
- Svelte 5 GUI: 6-area navigation shell, Models list, Model detail with
  action-eligibility panel, Register-local-checkpoint wizard (inspect then
  register), operational Overview. Evaluation/Atlas/Experiments/Comparisons
  show Milestone-N placeholders. Existing run table/detail retained under
  Evaluation.
- Tests: 17 new (10 unit + 7 integration); full suite 138 passed, ruff/mypy/
  format clean. Docs: `docs/gui-milestone-1.md` (repo-context + evidence).

## [0.8.0] - 2026-08-01

Phase 5: suite and comparison engine.

- New `eval_lab.analysis` package: weighted suite aggregation
  (`weighted.py`), label slicing (`slices.py`), paired A/B comparison
  (`comparison.py`), bootstrap CIs + significance (`statistics.py`,
  `significance.py`), regression detection (`regression.py`), Pareto frontier
  (`pareto.py`), and a pure `RunRow` data layer (`rows.py`).
- Weighted suites: composite score recomputed from suite per-task weights;
  raw unweighted aggregates always shown. Alternative weighting scenarios
  (spec 8.1B) via `configs/reports/*.yaml` and `--scenario`.
- Label slicing across domain/capability/modality/trajectory/failure-mode/
  difficulty, weighted and raw.
- Paired comparisons gate superiority on bootstrap CI width and sample size
  (no over-claiming on wide intervals). Regression reports include per-task
  deltas, pass/fail transitions and resource deltas.
- CLI `evaluate <suite> --model`, `compare <a> <b>`, `pareto`, writing
  Markdown suite/comparison reports to `reports/`.
- Dashboard: new `/api/models` endpoint (active models + run-time stats) and a
  Svelte model selector in the Runs filter + Overview card.
- Tests: 20 new (16 analysis unit, 3 Phase 5 integration, 1 dashboard models);
  full suite 121 passed, ruff/mypy/format clean.

## [0.7.0] - 2026-08-01

Dashboard (web UI): read-only eval-results viewer.

- Python FastAPI backend (`eval_lab.dashboard`) + read-only JSON API over
  `runs/runstore.db` and `runs/<id>/` artifacts: `/api/health`, `/api/overview`,
  `/api/runs` (with model/task/suite/status filters), `/api/runs/{id}`,
  `/api/runs/{id}/trace`, `/api/runs/{id}/telemetry` (per-node series).
- CLI `eval-lab serve` (FastAPI + uvicorn; `serve` extra). Built Svelte SPA is
  served from `dashboard/web/dist` when present.
- Svelte 5 + Vite SPA in `dashboard/web/` with an overview, filterable runs
  table, run detail (scores, ECharts telemetry line chart, trace log), and a
  tiny hash router. Dev server proxies `/api` to the backend.
- `RunStore` connections are now thread-safe (`check_same_thread=False`) so
  FastAPI can query them from the worker pool.
- Tests: 4 dashboard-API integration tests. `serve`/dashboard code is green
  under ruff, mypy and format.

## [0.6.0] - 2026-08-01

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

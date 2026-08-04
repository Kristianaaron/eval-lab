# Eval-Harness GUI — Milestone 3: Atlas Lab (genuine lightweight MoE tracer)

**Date:** 2026-08-04 · Resolves the pending M3 fork (handoff option **A**).

## Decision
The M3 fork was left pending with the default being **A · Genuine lightweight
MoE tracer**: build a real, synthetic mini-MoE and run a genuine CPU layerwise
router/expert forward pass to *measure* real per-layer/per-expert saliency — no
fabricated trace values. This was chosen over:
- **B · Progress simulator** — rejected: it fabricated trace numbers, violating
  the no-fabricated-outputs contract and requiring an M4 rewrite.
- **C · M4-only explore surface** — rejected: no M3 runtime to browse.

The tracer is eval-lab's own execution logic (option A), so the path is honest
and directly reusable by the M4 Explorer.

## What is implemented (all in `src/eval_lab/`)

**Tracer core (`atlas/` package)**
- `atlas/model.py` — `MiniMoE`: a tiny fixed-seed synthetic MoE (`num_layers ×
  num_experts` routed experts, top-k softmax). Each expert owns a preferred
  direction so calibration contexts produce non-trivial, reproducible routing.
  Weights are materialized from a seed (`config.json` + `weights.json`), and the
  forward-pass math below is actually executed.
- `atlas/tracer.py` — `CalibrationPool` (deterministic contexts, each token mixed
  with a capability-specific bias so different capability labels excite different
  experts); `trace_layer` runs one layer's router + experts over the whole pool,
  emitting real per-expert activation frequency, mean gate probability, and
  output-norm variance, plus per-label breakdowns. `LayerResult` is serializable
  so partial layers persist for recovery.
- `atlas/plans.py` — candidate prune topologies derived only from measured
  saliency (top-`k` by utilization-weighted `total_value`), producing the reserved
  `UnitKeepMap` layer selections with stable source-expert identity.
- `atlas/store.py` — `AtlasRunStore` owns the on-disk workspace
  (`atlas_out/atlas_runs/<id>/`: `run_manifest.json`, `layer_saliency.json`,
  `saliency_by_label.json`, `plans.json`, `keep_maps.json`, `trace.jsonl`, the
  auditable mini-MoE `source_model/`, and recovery state `_checkpoint.json` +
  `working/layer_{n}.json`). This matches the atlas-bridge consumer contract, so
  real M3 runs light up in the Explorer/Experiment surfaces unchanged.

**Orchestrated as a restart-safe job (`services/atlas_runtime.py`)**
- `AtlasRuntimeService` binds the tracer to the shared orchestrator under kind
  `atlas`: per-layer progress, **pause/resume at safe boundaries**, cancel, and
  recovery checkpoints (a paused/interrupted run resumes from the last finished
  layer). On completion it links the artifacts back to the source model asset
  (tags it `atlas-traced`).
- **Honest resource estimator**: probes one layer over a tiny pool to calibrate
  wall time, then multiplies across tokens × layers with a finalize multiplier —
  everything labelled `estimated`.

**API (`dashboard/api.py` `_register_atlas_runtime`)**
- `GET /api/atlas/config` (sources, suites, trace depths, capability labels,
  default topology + keep budgets), `POST /api/atlas/estimate`,
  `POST/GET /api/atlas-jobs`, `GET /api/atlas-jobs/{id}`,
  `POST /api/atlas-jobs/{id}/{cancel,pause,resume}`,
  `GET /api/atlas-runs[/{id}]` (typed run detail with real artifacts).
- Shared orchestrator wired across `/api/eval-jobs` and atlas (single job store).

**Orchestrator additions (`services/orchestrator.py`)**
- `JobOrchestrator.pause`/`resume`: `running → pausing → paused` at the next
  safe boundary, and `paused → resuming → running` resume from checkpoint.

**GUI (`dashboard/web/src/AtlasLab.svelte`)**
- Build-atlas wizard (left): source model / calibration suite / trace depth /
  keep-budget pickers + *Estimate resources* + *Build atlas* launch.
- Live job monitor (right): per-job stage + progress bar + state, with
  **Pause / Resume / Cancel** controls and polling while active jobs exist.
- Completed runs + deep-dive detail: candidate plans (kept/layer + resident
  bytes F32/BF16), keep-maps with source expert identity, measured saliency table.

## Verified
- Full-depth run live over HTTP: `estimate` → launch → `pause` (caught mid-trace
  at progress 1/6, state `paused`) → `resume` → `completed`.
- Genuine artifacts: 48 saliency rows (real mean/frequency/total_value/variance/
  activation_count), 3 keep-budget plans (`keep8-full`, `keep4-saliency`,
  `keep2-saliency`) with resident bytes scaling 98 KB → 49 KB → 24 KB, 6 keep-maps
  with source expert ids, 27,648 trace events, topology `synthetic_moe` 6L×8E·top-2.
- Integration tests: `tests/integration/test_atlas_runtime.py` (4) — complete-run
  persists real artifacts, pause/resume resumes from checkpoint, restart recovery
  flags+resumes, wizard API endpoints.
- **Bug fixed while exercising this**: `JobStore.save` used a single shared
  `.tmp` filename; worker-thread progress saves and API-thread pause/cancel saves
  raced and intermittently raised `FileNotFoundError` (`test_eval_job_cancel_marks_request`).
  Now each save uses a unique temp name with atomic rename (last writer wins with
  a full snapshot). Confirmed green 8/8 consecutive runs.
- Full suite **168 passed**; `ruff check`, `ruff format --check`, `mypy src` clean.
- Evidence via HTTP + tests + built bundle (no arm64 Chromium → no live-GUI shots).

## Recorded, still-unresolved dependencies
- Real runnable-model endpoints (OpenAI-compatible/SGLang/vLLM) — GUI-launched
  evals still use the deterministic mock adapter.
- Derivative *builder* (M6): M3 produces prune plans/keep-maps, but building and
  scoring an actual pruned derivative end-to-end is future work (Experiment M5
  currently pins a candidate plan from an imported run).
- Live per-node telemetry in `/api/environment` (returns configured envelope today).

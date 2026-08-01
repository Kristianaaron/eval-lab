# Eval-Harness GUI — Milestone 1 Report

**Status:** Milestone 1 complete (per spec §19, stop after M1 for review)
**Date:** 2026-08-01 · **Branch:** main · **Version:** 0.9.0

---

## A. §19 prerequisite — repository inspection

### 1. Frontend framework and component system
- **Svelte 5 (runes) + Vite SPA** at `dashboard/web/`, bundled to `dashboard/web/dist/` and served by FastAPI. Entry `main.js` mounts `App.svelte`.
- Hash-based router in `App.svelte` (`parse(hash)` → overview/models/evaluation/atlas/experiments/comparisons/model/:id/models/register), no router lib.
- Styling: single `app.css` with a dark theme via CSS custom properties (`--bg/--panel/--accent/--green/--red/--amber`).
- Existing views before M1: `Overview`, `Runs` (filterable run table), `RunDetail`; `lib/api.js` fetch helpers.

### 2. Backend APIs and services
- `src/eval_lab/dashboard/api.py` — read-only FastAPI over run data: `/api/health`, `/api/overview`, `/api/models`, `/api/runs`(+filters), `/api/runs/{id}`(+`/trace`, `/telemetry`). Serves the built SPA.
- No application-facing **service layer** existed; routes called `RunStore` directly. (Gap: spec §11 requires a stable typed service layer.)

### 3. Schemas relevant to models/suites/runs/telemetry/traces/reports
- `schemas/models.py`: `TaskSpec`, `SuiteSpec`, `ModelConfig`, `HarnessConfig`, `RunManifest`, `ScoreResult`, `TraceEvent` (all versioned Pydantic).
- `schemas/model_asset.py` (new, M1): `ModelAssetRecord`, `CheckpointInspection`, `ActionEligibility`, `EnvBudget`, request/result DTOs.
- Analysis schemas (`analysis/*`) from Phase 5 cover comparisons, slices, Pareto.

### 4. Worker/job infrastructure
- **None.** Runners (`direct`, `agent`, `batch`, `perf`) are synchronous in-process; no background job manager, no persistent job state machine, no progress-event stream. (Major dependency for Milestones 2/3 — atlas/eval job monitoring.)

### 5. Persistence layer
- `storage/sqlite.py` `RunStore` (runs + scores index) + portable JSON/JSONL artifacts under `runs/<id>/` (manifest/result/scores/trace/report).
- `storage/model_assets.py` (new, M1): JSON-file registry under `models/`.

### 6. Missing contracts needed by the spec (not in M1 scope)
- Atlas job model + state machine (§12 atlas/derv states), evaluation run state machine, resource estimator, keep-map/precision/residency-map schemas, source↔derivative expert identity, calibration↔held-out leakage registry, telemetry/hardware node status, event-streaming progress API.
- Enforcement: action-eligibility and model classification are provided in M1; the remaining flows consume them.

### 7. Proposed implementation order
Milestone 1 (this) → M2 evaluation launch/monitoring → M3 atlas job setup/monitoring (needs a background worker + persisted state machine) → M4 atlas exploration → M5 experiment creation → M6 derivative build + comparison. Matches spec §15.

### 8. Conflicts with existing architecture
- The read-only run API and SPA named it a “dashboard”; the spec needs a management GUI. This is additive, not a conflict.
- Existing runs are keyed by `model_id` string; the spec needs **registered model assets** (stable `asset_id`). M1 introduces assets as a separate first-class registry and does **not** retrofit the run pipeline onto it (a documented M2+ interface decision).
- `.gitignore` anchors `/reports/` to root so source `src/eval_lab/reports/` and `configs/reports/` remain tracked.
- No arm64 Chromium is available on this host, so live-GUI screenshots could not be captured (bundled headless Chrome is x86-64). Evidence is provided via API responses, test results, and the built bundle.

---

## B. Milestone 1 deliverables

### Backend
- **Typed schemas** `schemas/model_asset.py`: `ModelAssetRecord`, `CheckpointInspection`, `ActionEligibility`/`AvailableAction`, `EnvBudget`, request/result DTOs (all `extra="forbid"`).
- **Application service layer** `services/models.py`: `ModelAssetService` (`register_local_checkpoint`, `inspect` via inspection, `get/list/delete`, `eligibility`) + pure `resolve_available_actions(asset, budget)`.
- **Checkpoint inspection** `inspection/checkpoint.py`: reads `config.json` + SafeTensors **headers only** (never tensor payloads); detects model type/architecture/layers/routed experts/top-k/quantization, file & shard counts, stored size, per-dtype params and resident estimate; classifies `atlas_compatible` (sparse MOE) and `runnable_here` vs envelope.
- **Persistent registry** `storage/model_assets.py`: JSON-file store under `models/` (survives restarts; idempotent synthetic seeding on first start: `kimi-k3-official`, `deepseek-v4-flash`, `qwen3.5-2b-vision`, `k3-agent-96`).
- **API** (`dashboard/api.py`): `GET /api/models-assets`, `GET|DELETE /api/models-assets/{id}`, `GET …/{id}/actions`, `POST /api/models-assets` (register), `POST /api/models-assets/inspect` (mid-wizard, no registration), `POST …/fixtures`. Model routes are registered **before** the SPA static mount so the catch-all `/` no longer shadows them.
- **Oversized-source protection** is structural: `build_atlas` is the valid action for K3; `evaluate_directly` is disabled with an explanatory reason until a runnable endpoint or fitting envelope exists.

### Frontend (Svelte 5)
- **Nav shell** with the six top-level areas: Overview, Models, Evaluation, Atlas Lab, Experiments, Comparisons. Evaluation/Atlas/Experiments/Comparisons show Milestone-N placeholders (no fabricated functionality).
- **Models list** — cards with type badge, stored/resident size, architecture, atlas compatibility, warnings, delete; “Register model” action.
- **Model detail** — full asset table + **action-eligibility panel** rendering each action as available/enabled or unavailable-with-reason (e.g. direct eval of K3 disabled with an explanation), plus warnings and provenance (parent/atlas).
- **Register-local-checkpoint wizard** — 1) path/name → 2) *Inspect checkpoint* (streams a real inspection: model type, layers, experts, top-k, shards, sizes, atlas/runnable classification, recommended *Build atlas* for sparse checkpoints) → 3) *Register model* → navigates to the new asset.
- **Overview** — operational cards (model/runnable/source counts, active jobs, hardware envelope) + shortcuts; not a decorative analytics board.
- **Retained existing functionality**: run table + run detail are reachable under Evaluation (unchanged), plus the model-selector feature.

---

## C. Tests and evidence

New:
- `tests/unit/test_model_assets.py` (10) — eligibility rules (oversized source, runnable, remote, keep-map/compare gating) + inspection classification (sparse, missing config, non-dir, memory-envelope).
- `tests/integration/test_model_assets_api.py` (7) — fixture seeding, detail+eligibility, register→persist→reload, invalid path, delete, type derivation from inspection.
- `tests/conftest.py` — synthetic real SafeTensors checkpoint builder (no full-model load; CI-safe).

Full suite: **138 passed** (was 121; +17 M1). `ruff check`, `ruff format --check`, `mypy src` all clean (70 source files).

Exit gate (spec §19 M1) — demonstrated:
- user can register a fake/small checkpoint → `POST /api/models-assets` + inspect endpoint, verified via TestClient + live curl;
- inspection results render correctly → detail/inspect API returns classification; SPA bundles the views;
- impossible actions show explanatory reasons → `resolve_available_actions` returns `{evaluate_directly: {available: false, reason: "…exceeds the current memory budget."}}`, shown in the UI as disabled-with-reason;
- state persists across restart → JSON registry on disk (`models/*.json`) re-read on new `ModelAssetService`; verified by re-loading a freshly registered asset.

Note: live GUI screenshots were not captured — no arm64 Chromium exists on this host (bundled headless Chrome is x86-64, ENOEXEC). All interactive evidence above is over the real running server (`127.0.0.1:8100`) via HTTP and the Svelte build.

---

## D. Unresolved backend dependencies (recorded, not silently mocked)
1. **Background job/worker layer with persistent state machines** (all of M2/M3 job flows).
2. **Atlas runtime** (layerwise trace, saliency/keep-map computation) — the CLI/schema contracts are reserved by Phase 8 trace fields, not implemented.
3. **Real model endpoints** for direct evaluation (OpenAI-compatible + vLLM/SGLang adapters exist; a GUI-facing evaluation service is M2).
4. **Hardware/node telemetry API** to populate live memory/NVMe in the Overview.
5. **Leakage registry** connecting calibration suites to held-out promotion gating.

# Eval-Harness GUI — Milestone 2 + Architecture Corrections

**Date:** 2026-08-01 · Implemented after the architecture-validation report (`ARCHITECTURE_VALIDATION_REPORT.md`).

## Corrections applied (all seven, no rewrite)

1. **Persisted Job Orchestrator** — `schemas/job.py` (12-state machine with validated transitions), `storage/jobs.py` (atomic JSON), `services/orchestrator.py` (background workers, real stage/progress, safe-boundary cancel, restore-on-restart). Jobs survive GUI restarts; orphaned active jobs become `failed_recoverable` + `interrupted`.
2. **Task `data_partition`** + leakage guard — `schemas/models.py` `TaskSpec.data_partition` (`atlas_calibration|development_evaluation|held_out_evaluation|unset`); `services/leakage.py` flags overlap and blocks held-out treatment. Evaluation jobs record and warn on detected leakage.
3. **Service boundaries** — `EvaluationService` (launch/monitor/cancel of eval jobs over the existing runners), `ComparisonService` (wraps the Phase 5 analysis engine: compare/slices/pareto). Backend run-API reads remain thin read-only adapters; forward-facing flows go through the services.
4. **Atlas as sibling, not in the evaluator** — no coupling added; execution logic stays separate (atlas runtime is a future subsystem).
5. **Reserved atlas schemas** — `schemas/atlas.py`: `EvidenceLevel`, `EvidenceKind` (measured/estimated/predicted/inferred/causally_tested), `ExpertIdentity` (source id never overwritten), `AtlasTraceField`, `AtlasRunManifest`.
6. **Environment service** — `/api/environment`; Overview no longer hard-codes node/memory/version.
7. **Overview env facts de-hard-coded** (via #6).

## Milestone 2 (exit gate)

- **Existing harness launched from the GUI**: `POST /api/eval-jobs` runs the real `DirectRunner`/`run_suite` path in a background job; verified live (5-task suite → 5 auditable runs).
- **Run records remain auditable**: each task writes `runs/<id>/{manifest,result,scores,trace,report}.md` and the SQLite index; every run links back from the job result.
- **Interrupted runs show correct state**: jobs persist state; on process restart, still-active jobs are flagged `failed_recoverable`/`interrupted`.
- GUI: Evaluation wizard + live progress monitor + cancel-at-boundary + results; generic Jobs area; Overview from the environment service.

## Verified
- Live server: `/api/environment`, `/api/eval-config`, `/api/eval-jobs` launch→completed (5 runs, leakage `[]`), `/api/jobs`, `/api/comparisons/{pareto,slices}`.
- Tests: **149 passed** (was 138; +11 job/leakage/platform). `ruff check`, `ruff format --check`, `mypy src` clean.
- Evidence via HTTP + tests + built bundle; no live-GUI screenshots (no arm64 Chromium on this host).

## Recorded, still-unresolved dependencies
- Real runnable model endpoints (OpenAI-compatible/SGLang/vLLM) for non-mock evaluation — currently every GUI-launched run uses the deterministic mock adapter.
- Atlas runtime / experiment manager / derivative builder (future milestones).
- Live per-node telemetry in the environment endpoint (returns configured target envelope today).

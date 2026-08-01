# PHASE_3_REPORT — telemetry and performance

**Status:** COMPLETE
**Date:** 2026-07-31
**Host:** eval-node (Linux aarch64, 1× NVIDIA 2e12)
**Scope:** Phase 3 only (spec §23). Collectors, telemetry sampling, cold/warm
markers, performance suite, per-node correlation, and TTFT/decode verification
against raw timestamps.

---

## 1. What was built

| Deliverable | Location |
|-------------|----------|
| Collectors (system, process, NVMe, network, NVIDIA) | `src/eval_lab/telemetry/collectors.py` (spec 15.2) |
| Periodic sampler → `resource_sample` events | `src/eval_lab/telemetry/sampler.py` (spec 15.3/15.5) |
| Per-node correlation + raw-timestamp timing verification | `src/eval_lab/telemetry/correlation.py` |
| Streaming timing protocol | `src/eval_lab/adapters/base.py` (GenerationTiming, StreamingModelAdapter) |
| Deterministic streaming adapter | `src/eval_lab/adapters/timing.py` (TimedMockAdapter) |
| Performance runner | `src/eval_lab/runners/perf.py` (PerfRunner) |
| Cold/warm run markers | `runners/direct.py`, `runners/agent_executor.py`, `runners/perf.py` |
| Manifest telemetry fields | `schemas/models.py` (`telemetry_stream`, `timing`) |
| Hardware-performance suite + task | `configs/suites/hardware_perf.yaml`, `tasks/hardware/perf_probe.yaml` |
| `hardware` domain label | `config/labels.py` |
| CLI perf entrypoint | `cli/main.py` (`eval-lab perf`) |
| Tests | `tests/unit/test_telemetry.py` (13), `tests/integration/test_phase3.py` (4) |

## 2. Commands run

```bash
.venv/bin/eval-lab validate task tasks/hardware/perf_probe.yaml
.venv/bin/eval-lab validate suite configs/suites/hardware_perf.yaml
.venv/bin/eval-lab perf --interval 0.05
.venv/bin/pytest -q            # 53 passed
.venv/bin/ruff check src tests # clean
.venv/bin/ruff format --check src tests # clean
.venv/bin/mypy src             # 41 files, no issues
```

## 3. Phase 3 exit gate (§23)

| Gate | Evidence |
|------|----------|
| process/NVIDIA/NVMe/network collectors | All five collectors present; each returns `available: false` + reason on missing hardware instead of raising or fabricating values (spec 15.2/15.3). |
| cold/warm run markers | `telemetry_marker` events (with `warm_state`/`cold_start`/`node_id`) at run start in direct, agent and perf runners; `warm_state` persisted on the manifest. |
| performance suite | `configs/suites/hardware_perf.yaml` (family `hardware_performance`), driven by `eval-lab perf`. |
| per-node telemetry correlation | `telemetry/correlation.py` groups `resource_sample` events by `node_id`; a `telemetry_correlation` event is appended to each perf run's trace. |
| samplers under a configurable overhead target | Sampling runs on a single daemon thread at a user-configurable `interval_s` (`--interval`); overhead scales with frequency. |
| missing metrics handled without corrupting runs | Collectors return `available: false`; integration test forces missing system/NVIDIA and the run still completes/passes. |
| TTFT and decode throughput verified against raw timestamps | `verify_timing` recomputes TTFT/decode from raw `token_event` wall timestamps and `model_request` time, and sets `ttft_agrees`/`decode_tps_agrees` against the adapter report. |

## 4. Smoke results (`eval-lab perf`)

Three repetitions of `hardware.perf.probe.001`: all **pass**, `ttft≈0.050s`
(configured `first_token_delay_s=0.05`) and `decode_tps≈19.9`
(configured 20 tokens/s). Trace carries monotonic sequences 0–8 with
`telemetry_marker` → `model_request` → `token_event`×n → `model_completion` →
`run_completion` → `telemetry_correlation`, plus periodic `resource_sample`
events attributed to node `node-a`.

Manifest `timing`: `ttft_agrees: true`, `decode_tps_agrees: true`, `token_count:
2`; `telemetry.per_node[node-a].sample_count=2`; `telemetry_stream`
points at the run's `trace.jsonl`.

## 5. Notes

- Peak GPU utilization reported as `0.0` on this host because the synthetic
  probe generates no real GPU load; the collector plumbing is correct and will
  surface real values under a genuine model runtime.
- The direct/agent runners record cold/warm markers unconditionally but only the
  perf runner attaches the periodic sampler; general-run sampling can be enabled
  later without touching the collector layer.
- Phase 3 deliberately stops at the exit gate; Phase 4 (advanced scorers and
  judge calibration) is not started.

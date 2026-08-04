# HANDOFF — eval-lab (M1–M6 built; M3 Atlas Lab just shipped)

**Session end.** Everything committed and pushed; server running. Pick up here.

## 1. Live state right now
- Dashboard/GUI running on the host, latest code:
  `http://100.96.194.44:8100` (tailnet IP), HTTP same port.
- Server launched: `nohup .venv/bin/python -m eval_lab.cli.main serve --host 0.0.0.0 --port 8100`
  (log `/tmp/eval-lab-dash.log`). Restart after any backend change:
  `pkill -f "eval_lab.cli.main serve"` then re-run.
- Repo: `eval-lab`, branch `main`. Remote `origin` = github.com/Kristianaaron/eval-lab.

## 2. Shipped (all committed)
- **Harness core (P0–P6)** + comparison engine (P5), 38-task catalogue, suites.
- **GUI M1** (model-asset registry, SafeTensors header inspection, action eligibility)
  and **GUI M2** (job orchestrator with restore-on-restart, leakage guard, eval
  wizard/monitor/cancel, comparisons, experiments).
- **M4 Explorer** (cross-registry browse + run deep-dive) and refined Evaluation
  UX (config-left + per-domain rows).
- **M3 Atlas Lab (this session, just shipped, v0.17)** — genuine lightweight MoE
  tracer (handoff option A): synthetic `MiniMoE` + real CPU layerwise router/
  expert forward pass measuring per-layer/per-expert saliency; runs as a
  restart-safe `atlas` orchestrator job with per-layer progress, **pause/resume
  at safe boundaries**, cancel, and recovery checkpoints. Writes
  atlas-bridge-compatible `atlas_out/atlas_runs/<id>/` artifacts; plans/keep-maps
  derived from measured saliency only. Verified live over HTTP (pause at 1/6 →
  resume → completed; real 48-row saliency, 3 plans, 6 keep-maps, 27k trace
  events). Report: `docs/gui-milestone-3.md`.
- **M5 experiments** (pin a candidate plan from an imported run) and **M6
  derivative-builder** surfaced earlier; see CHANGELOG.

## 3. Bug fixed this session
- `JobStore.save` used one shared `.tmp` filename; worker-thread progress saves
  and API-thread pause/cancel saves raced → intermittent `FileNotFoundError`.
  Now each save uses a unique temp name with atomic rename. Full suite green.

## 4. Key new files
- `src/eval_lab/atlas/{model,tracer,plans,store}.py`
- `src/eval_lab/schemas/atlas_runtime.py`, `src/eval_lab/services/atlas_runtime.py`
- `tests/integration/test_atlas_runtime.py` (4 tests)
- `docs/gui-milestone-3.md`, `dashboard/web/src/AtlasLab.svelte`
- Orchestrator: `src/eval_lab/services/orchestrator.py` (pause/resume)
- API: `src/eval_lab/dashboard/api.py` (`_register_atlas_runtime`)

## 5. Open dependencies (not silently mocked)
- **Real runnable-model endpoints** (OpenAI-compatible/SGLang/vLLM) — every
  GUI-launched eval still uses the deterministic mock adapter.
- **Derivative builder (M6)** — M3 produces prune plans/keep-maps, but building
  and scoring an actual pruned derivative end-to-end is future work.
- Live per-node telemetry in `/api/environment` (returns configured envelope).

## 6. Gotchas
- `dist/` under `dashboard/web` is gitignored — SPA is a build-time artifact,
  rebuilt with the source; keep the served bundle current after SPA edits.
- No arm64 Chromium on this host → can't capture live-GUI screenshots (evidence
  via HTTP/tests/built bundle).
- `.gitignore` anchors `/reports/`, `/models/`, `/jobs/`, `/atlas_out/`,
  `/experiments/` to root so runtime output stays untracked while source stays
  tracked.
- To QA: `eval-lab doctor`, `run suite`, `compare`, `pareto`, `evaluate`.

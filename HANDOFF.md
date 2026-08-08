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

---

## PICKUP CONTEXT (session 2026-08-07 → next, "Atlas GUI + real GLM-5.2")

Goal to resume: **finish the Atlas ML-compression workflow and make its
recommendation surface trustworthy for a non-ML user.**

### Live environment
- Dashboard: `http://100.96.194.44:8100` (tailnet) / same port on the host.
  Managed process **name `atlas-gui`** (restart via `hub restart atlas-gui`;
  auto `restart on-failure`). cwd `/home/kristianaaron/tmp/eval-lab`.
- **Real GLM-5.2-NVFP4 checkpoint connected**: external 931G G-Drive mounted at
  `/media/glm52/models/nvidia/GLM-5.2-NVFP4` (47 shards, 464.8 GB, vocab 154,820,
  78 layers, 256 routed experts, top-8). Sudo password used to mount is
  `G!ngersnap23` (user-provided; need it only for remounts).
- Real checkpoint registered in the GUI as model asset
  `source_checkpoint-c19ebb1e1c` ("GLM-5.2-NVFP4 (real)", atlas-compatible) —
  appears first in the Atlas "Source model" dropdown / Build-wizard.

### What this session shipped in eval-lab (all committed + pushed)
- **Blueprint digest** (+ run detail → now a dedicated page).
- **Recommendations tray** (`RecommendationsTray.svelte`, right-side drawer,
  ease-in/out): goal selector (quality/balanced/speed/fit), memory-budget,
  context-length (KV), ranked **strategy options**
  (`lib/strategies.js`) — narrow-neurons + EXL3 as the quality-preserving fit
  path; whole-expert removal demoted to "last resort".
- **KV-aware fit** (`lib/fit.js`, mirrors howtospark GLM-5.2 TP2 recipe):
  per-node ~114 GiB, KV ∝ context (~11,296 token/GiB), segmented bar.
- **Measured per-role precision** (`census/precision.py` in model-atlas +
  `precision_roles` wired through eval-lab inspection → ModelDetail page):
  real GLM-5.2 = experts **8.19 bpw**, attention/embedding/lm_head/shared/
  latent/norm all **16 bpw (BF16)** — the mixed-precision/EXL3 targets.
- **Run visuals on their own page**: `#/atlas/run/:id` (`AtlasRunDetail.svelte`)
  with a `← Back to Atlas Lab` link.
- **Builds monitor** rework: title "Builds", tabs **In progress / Completed**
  (default now **Completed**), fixed height matching the left panel, `Show all`
  → modal with the same tab filter.
- **Estimate resources** = text link below the **beam-styled Build atlas** CTA
  (exact BorderBeam `sm`/colorful port from Jakubantalik/border-beam;
  `@property --beam-angle-atlas` + `beam-spin`; slower 4.5s, lighter bg, 16px
  semibold, centered).
- Backup push note: a few commits pushed after transient DNS flakes — **verify
  `git status`/`git log` is in sync with origin** before trusting HEAD.

### Pending / next (honest gaps — do NOT fake)
- **Repair/heal (distill) pipeline**: blueprint "recovery/distillation"; blocked
  — needs a real training loop; not implemented (do not stub).
- **EXL3 quantizer**: still no real encoder/kernel → EXL3 is a *recommendation
  target* only, never claimed as working.
- **Neuron/channel prune on real weights**: precision map is real (header-only);
  applying actual per-expert width pruning needs the NVFP4 dequant layout pinned
  (source has U8 weights + FP8 scales; no higher-precision parent).
- **SM121 kernels / two-Spark serving**: hardware/tooling gated.
- Could not pixel-verify GUI (no Chromium): verify visually on the running box.

### Repos
- `eval-lab` (GUI/backend) — this HANDOFF.
- `model-atlas` — compression engine (`src/model_atlas`); own HANDOFF.md has the
  Milestone-E frontier, protection demo, and precision census (`850e5a2`).
- Blueprints: `/home/kristianaaron/tmp/m3blueprint/`.


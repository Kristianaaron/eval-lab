# eval-lab

Agent-agnostic local model and agent evaluation harness.

Versioned schemas, label registry, YAML task loader, direct/agent/perf
runners, deterministic + advanced scorers, LLM judge calibration, telemetry,
and a 38-task catalogue.

## Dashboard (web UI)

Read-only eval-results dashboard: Python (FastAPI) backend + Svelte SPA.

```bash
uv pip install -e '.[serve]'      # FastAPI + uvicorn
.venv/bin/eval-lab serve --port 8100   # serves API + built SPA
open http://127.0.0.1:8100
```

The API is read-only over `runs/runstore.db` + `runs/<id>/` artifacts. Endpoints:
`/api/health`, `/api/overview`, `/api/runs`, `/api/runs/{id}`,
`/api/runs/{id}/trace`, `/api/runs/{id}/telemetry`.

### Frontend development

```bash
cd dashboard/web
npm install
npm run dev        # Vite dev server, proxies /api to :8100
npm run build      # emit dashboard/web/dist (served by `eval-lab serve`)
```

See `docs/architecture.md`, `docs/data-contracts.md`, and `docs/adr/`.
See `PHASE_0_REPORT.md`, `PHASE_3_REPORT.md`, `PHASE_4_REPORT.md`, `PHASE_6_REPORT.md`
for phase exit-gate evidence.

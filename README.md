# eval-lab

Agent-agnostic local model and agent evaluation harness — and a standalone
benchmark for the models you serve locally.

Versioned schemas, label registry, YAML task loader, direct / agent /
perplexity runners, deterministic + hidden-test scorers, LLM judge
calibration, telemetry, a scorecard, and a 60+ task catalogue.

## Standalone benchmark (quick start)

```bash
uv venv .venv && uv pip install -e '.[dev,serve]'

# run every benchmark group against an OpenAI-compatible endpoint
.venv/bin/eval-lab benchmark --model my-model-q4 \
    --endpoint http://127.0.0.1:8000/v1 --model-name my/model --api-key-env MY_KEY

# perplexity / bits-per-byte only (vLLM, SGLang, or --provider hf_local)
.venv/bin/eval-lab perplexity --model my-model-q4 --endpoint http://127.0.0.1:8000/v1 --model-name my/model
```

Groups: **core** (capabilities), **coding_deep** (multi-part specs with hidden
test suites + repository-level agentic tasks), **long_context** (multi-hop
retrieval at 8k–64k tokens, log aggregation, whole-repo bug hunt) and
**perplexity**. The scorecard is written to `reports/` and shown on the
dashboard's Benchmark page. See `docs/benchmark.md`.

## Dashboard (web UI)

Read-only eval-results dashboard: Python (FastAPI) backend + Svelte SPA.

```bash
uv pip install -e '.[serve]'      # FastAPI + uvicorn
.venv/bin/eval-lab serve --port 8100   # serves API + built SPA
open http://127.0.0.1:8100
```

To evaluate a real model from the UI, open **Models → Register model →
OpenAI-compatible endpoint**, enter the server base URL and model name, then
open **Evaluation** and choose the registered model. API keys are read from
the environment variable you name and are never stored in the registry.
The built-in mock model remains available for an offline smoke test.

The API is read-only over `runs/runstore.db` + `runs/<id>/` artifacts. Endpoints:
`/api/health`, `/api/overview`, `/api/runs`, `/api/runs/{id}`,
`/api/runs/{id}/trace`, `/api/runs/{id}/telemetry`, `/api/runs/{id}/perplexity`,
`/api/benchmark/groups`, `/api/benchmark/scorecard?model_id=`,
`/api/benchmark/models`, `/api/perplexity`.

### Frontend development

```bash
cd dashboard/web
npm install
npm run dev        # Vite dev server, proxies /api to :8100
npm run build      # emit dashboard/web/dist (served by `eval-lab serve`)
```

See `docs/benchmark.md`, `docs/architecture.md`, `docs/data-contracts.md`, and `docs/adr/`.
See `PHASE_0_REPORT.md`, `PHASE_3_REPORT.md`, `PHASE_4_REPORT.md`, `PHASE_6_REPORT.md`
for phase exit-gate evidence.

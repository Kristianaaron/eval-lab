# eval-lab

A local evaluation harness for LLMs and agents. Point it at any OpenAI-compatible
endpoint, pick a suite, and get scored, reproducible runs with a web dashboard
to inspect them. It is built to take candidates straight from
[Cebu Profiler](https://github.com/Kristianaaron/cebu-profiler) (quantized
models) and tell you how much quality they kept.

## What's in it

- **Tasks and suites.** 54 YAML tasks across 20 categories (reasoning,
  mathematics, coding, frontend, tool calling, long context, safety, legal,
  finance, health, multilingual and more), grouped into weighted suites under
  `configs/suites/`.
- **Runners.** Direct (single prompt), agent (multi-turn with tools),
  batch, perf (hardware telemetry), and context-pressure.
- **Scorers.** `exact`, `regex`, `json_schema`, `unit_test`, `trajectory`,
  `artifact`, `visual`, and `perplexity` (from token logprobs). Results are
  aggregated per task with weights and required gates.
- **LLM judges** with calibration against a human gold set (`gold/`).
- **Comparison tools.** Paired A/B runs on the same tasks, weighted
  label-sliced reports, and a quality-vs-latency Pareto frontier.
- **Held-out mode.** `--require-held-out` refuses tasks that aren't
  partitioned as held-out, so candidate scores aren't contaminated by
  calibration data.
- **Run store.** Every run writes a manifest (seed, sampling, budgets),
  trace, scores and telemetry to `runs/<id>/` and indexes it in
  `runs/runstore.db`.

## Quick start

Requires Python 3.12+ and [uv](https://github.com/astral-sh/uv).

```bash
make dev                      # create .venv and install with dev extras
.venv/bin/eval-lab doctor     # check the environment
.venv/bin/eval-lab list       # list available tasks
```

Run a suite against a model served behind an OpenAI-compatible API (vLLM,
llama.cpp, SGLang, TensorFold, ...):

```bash
.venv/bin/eval-lab run suite configs/suites/smoke_direct.yaml \
  --model my-model \
  --endpoint http://127.0.0.1:8080/v1 \
  --model-name served-model-name \
  --seed 17 --temperature 0.0
```

`--model` is the id the run is stored under. Without it (or with
`--model mock`) eval-lab uses the built-in deterministic mock adapter.

Then inspect results:

```bash
.venv/bin/eval-lab list-runs
.venv/bin/eval-lab score <run-id>
.venv/bin/eval-lab report <run-id>
```

Run `eval-lab <command> --help` for all options. Other commands: `validate`,
`perf`, `evaluate`, `compare`, `pareto`, `calibrate-judge`, `atlas`.

## Dashboard

A FastAPI backend with a Svelte front end, served over the run store.

```bash
uv pip install -e '.[serve]'
.venv/bin/eval-lab serve --port 8100
open http://127.0.0.1:8100
```

To evaluate a real model from the UI, open **Models → Register model →
OpenAI-compatible endpoint**, enter the base URL and model name, then choose
it under **Evaluation**. API keys are read from an environment variable you
name and are never stored. A built-in mock model is available for an offline
smoke test.

API endpoints: `/api/health`, `/api/overview`, `/api/runs`, `/api/runs/{id}`,
`/api/runs/{id}/trace`, `/api/runs/{id}/telemetry`.

Front-end development:

```bash
cd dashboard/web
npm install
npm run dev     # Vite dev server, proxies /api to :8100
npm run build   # writes dashboard/web/dist, served by `eval-lab serve`
```

## Cebu Profiler integration

`eval-lab atlas` and the dashboard's Cebu section connect to a running Cebu
Profiler (default `http://127.0.0.1:8011`). Quantized candidates it produces
can be imported with their fit facts (precision, residency, coverage) and
evaluated on held-out suites such as `configs/suites/atlas-glm52-heldout.yaml`.
The profiler is optional; eval-lab works on its own.

## Development

```bash
make test     # pytest
make lint     # ruff
make check    # ruff + mypy + format check
```

## Layout

```
src/eval_lab/   adapters, runners, scorers, judges, services, storage, cli, dashboard
tasks/          task definitions (task.yaml + prompt.md per task)
configs/        suites, judges, report weights
gold/           human-labelled judge calibration set
dashboard/web/  Svelte front end
docs/           architecture, data contracts, ADRs
tests/          unit and integration tests
```

Design notes: `docs/architecture.md`, `docs/data-contracts.md`, `docs/adr/`.
Phase exit-gate evidence: `PHASE_*_REPORT.md`.

## License

Apache-2.0

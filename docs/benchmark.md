# The eval-lab standalone benchmark

eval-lab ships a fixed, versioned benchmark you can point at any model you
serve locally (vLLM, SGLang, llama.cpp server, LM Studio, Ollama, …) or at a
local Hugging Face checkpoint, and get a scorecard that is comparable across
runs, quantizations and pruned derivatives.

```bash
uv pip install -e '.[dev,serve]'

# 1. Everything, one command (writes reports/scorecard_<model>.md, indexes runs)
eval-lab benchmark --model qwen3-32b-q4 \
    --endpoint http://127.0.0.1:8000/v1 --model-name Qwen/Qwen3-32B-AWQ \
    --api-key-env VLLM_API_KEY

# 2. Only some groups
eval-lab benchmark --model qwen3-32b-q4 --endpoint … --model-name … \
    --groups coding_deep,long_context

# 3. Perplexity alone, on the bundled corpora or on any text file
eval-lab perplexity --model qwen3-32b-q4 --endpoint … --model-name …
eval-lab perplexity ~/corpora/wikitext2-test.txt --model qwen3-32b-q4 --endpoint … --model-name …

# 4. Re-render the scorecard from stored runs; compare two models
eval-lab benchmark --model qwen3-32b-q4 --scorecard-only
eval-lab compare qwen3-32b-q4 qwen3-32b-nvfp4
```

The dashboard (`eval-lab serve`) shows the same data: **Benchmark** page for
scorecards, per-window perplexity charts and the cross-model leaderboard;
**Evaluation → Standard benchmarks** launches a group as a tracked job.

## Groups

| group | suite | what it measures | oracle |
|---|---|---|---|
| `core` | `configs/suites/benchmark-core.yaml` | reasoning, mathematics, instruction following, structured output, tool use, frontend basics, safety | exact / regex / json / unit tests |
| `coding_deep` | `configs/suites/benchmark-coding-deep.yaml` | eight multi-part specifications (caches, evaluators, schedulers, JSONPath, …) each with 15–35 hidden tests; three repository-level agentic tasks (bug hunt across a package, feature from spec, 40-call-site API migration) | `python_tests` partial credit + visible test command |
| `long_context` | `configs/suites/benchmark-long-context.yaml` | four multi-hop questions over generated policy compendia at ~8k / ~32k / ~64k tokens, windowed aggregation over a ~32k-token service log, and a whole-repository bug hunt answered from one prompt | `json_exact` (per-question credit), `python_tests` |
| `perplexity` | `configs/suites/benchmark-perplexity.yaml` | teacher-forced perplexity, bits/token and bits/byte on three fixed corpora (original prose, technical docs, Python source) | `perplexity` |

Every task declares its own runner: `direct` (single prompt, attachments
inlined), `agent` (tool loop in an isolated workspace with native tool
calling: `shell`, `file_read`, `file_write`, `list_files`), or `perplexity`.
Scores are 0–1 per task; the scorecard reports the mean score and pass rate
per group and per label domain from the latest completed run of each task.

## Perplexity

Perplexity is the most sensitive early signal of damage from quantization or
pruning, and it needs no judge. eval-lab computes it by asking the backend for
the log-probability of every token of a fixed corpus:

- **OpenAI-compatible servers**: `POST /v1/completions` with `echo: true,
  logprobs: 1, max_tokens: 1` (vLLM and SGLang support this; llama.cpp server
  does not return prompt log-probs, so use the `hf_local` provider for GGUF
  models via a transformers-loadable checkpoint or compare on a vLLM host).
- **Local checkpoints**: `--provider hf_local --model-name /path/to/checkpoint`
  (needs `uv pip install -e '.[hf]'`; torch + transformers) runs a true
  teacher-forced forward pass and is the reference measurement.

The corpus is scored in windows of `window_chars` characters (default 6 000).
Reported numbers:

| metric | meaning |
|---|---|
| `perplexity` | `exp(mean token NLL)` — depends on the tokenizer; compare only same-tokenizer models |
| `bits_per_token` | `mean NLL / ln 2` |
| `bits_per_byte` | `total NLL / (ln 2 · UTF-8 bytes)` — tokenizer-independent, use it across model families |

The `perplexity` oracle maps perplexity to a 0–1 score (`1 − ln(ppl)/ln(1000)`,
so ppl 1 → 1.0, 10 → 0.67, 100 → 0.33) and can gate on `max_perplexity`. A
backend that cannot return log-probabilities produces a run with
`status = error`, never a fake number.

Bundled corpora are small (2–3k tokens each) so the group runs in seconds; for
publication-grade numbers point `eval-lab perplexity` at a standard corpus
(WikiText-2 test, a Gutenberg text) that you fetch yourself — the metric code
is identical.

## Hidden-test coding tasks

`python_tests` runs a stdlib `unittest` suite that ships with the task but is
never shown to the model:

- *extract* mode (direct tasks): the largest fenced ```python block in the
  reply becomes `solution.py` next to the tests.
- *workspace* mode (agent tasks): the tests are copied into the sandbox the
  agent worked in and run against the files it left behind.

Score = fraction of tests passed, `passed` requires `min_pass_fraction`
(1.0 by default). A syntax error or missing symbol is a legitimate 0 with the
loader error attached to the run. Every hidden suite in the repository is
validated in CI against a reference solution (`tests/fixtures/reference_solutions`)
that must score 1.0 while a naive answer must not.

## Long-context tasks

`scripts/generate_long_context.py` regenerates the handbook and log packages
deterministically (seeded); answers are computed from the generated data and
written into `task.yaml`, so the oracle is exact by construction. Each
question needs facts from distant sections (a supersession reference, a
summary table, the staff directory in the appendix), so a model that only
reads the neighbourhood of the question cannot score. The repository bug hunt
gives the full listing of a 19-file library and asks for the corrected file;
the fix is only findable by reconciling the README contract with the
implementation.

## Adding your own task

Create `tasks/<domain>/<slug>/task.yaml` + `prompt.md` (+ `data/`, `workspace/`,
`tests/`), run `eval-lab validate task <path>`, and add it to a suite. Labels
must come from `src/eval_lab/config/labels.py`. Runner and oracle types are
listed by `eval-lab doctor --json`.

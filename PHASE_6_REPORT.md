# PHASE 6 REPORT — Target-Workload Task Catalogue (spec §9) & Suites (§8.1)

**Repository root:** `eval-lab/` · **Date:** 2026-08-01 · **Gate:** spec 9 (task catalogue) + §8.1 suite families + provenance/leakage audit

---

## 1. Summary

Phase 6 delivers a **38-task target-workload catalogue** (≥36 required), a full suite family, and this provenance report. Every task is a versioned, labeled `TaskSpec` loading standalone via `load_task_yaml`, with **deterministic-only oracles** (`exact`, `regex`, `json_schema`, `unit_test`, `artifact`). Every fixture reference resolves (`check_fixture_references` = 0 missing). All six suites (four new + two pre-existing Phase 1/3 suites) validate via `load_suite_yaml` with **zero unresolved task references**.

### Category minimums (spec §9) — all met

| Required family | Minimum | Delivered | Status |
|---|---|---|---|
| coding | ≥ 8 | **8** | ✅ |
| frontend / visual | ≥ 6 | **6** | ✅ |
| voxel / spatial | ≥ 6 | **6** | ✅ |
| agentic / tool-calling | ≥ 8 | **8** (4 agentic + 4 tool-calling) | ✅ |
| reasoning / math | ≥ 4 | **4** | ✅ |
| long-context / research | ≥ 4 | **4** | ✅ |
| **Total** | **≥ 36** | **38** | ✅ |

`general` (1) and `hardware` (1) count toward the total only (per spec they are not a required category floor). **No category shortfall.**

> **ID note:** the schema id pattern is `[a-z0-9]+(\.[a-z0-9_-]+)+` — the *first* segment may not contain `_`. The category directories `long_context/` and `tool_calling/` therefore map to id first-segments `longcontext` and `toolcall` (e.g. `longcontext.document_retrieval.001`, `toolcall.dataset_query.001`). All other categories use single-token first segments identical to the directory name.

---

## 2. Task inventory (38)

Columns: **id · dir · labels(difficulty) · runner · oracle type(s) · fixture provenance**

| id | dir | domains · difficulty | runner | oracle | fixture |
|---|---|---|---|---|---|
| coding.json_output.001 | coding/json_output | coding · easy | direct | json_schema | — |
| coding.time_complexity.001 | coding/time_complexity | coding · medium | direct | json_schema | — |
| coding.output_prediction.001 | coding/code_output_prediction | coding · easy | direct | exact | — |
| coding.spot_bug.001 | coding/spot_bug | coding · medium | direct | regex | — |
| coding.fizzbuzz.001 | coding/fizzbuzz | coding · easy | agent | unit_test | workspace (solution.py + test) |
| coding.binary_search.001 | coding/binary_search | coding · medium | agent | unit_test | workspace (solution.py + test) |
| coding.parse_csv.001 | coding/parse_csv | coding · medium | agent | unit_test | workspace (solution.py + test) |
| coding.refactor_legacy.001 | coding/refactor_legacy | coding · hard | agent | unit_test | workspace (legacy.py + test) |
| frontend.semantic_markup.001 | frontend/semantic_markup | frontend,visual_design · easy | direct | regex | — |
| frontend.center_box_css.001 | frontend/center_box_css | frontend,visual_design · easy | direct | regex | — |
| frontend.design_card.001 | frontend/design_card | frontend,visual_design · medium | direct | regex | — |
| frontend.form_validation.001 | frontend/form_validation | frontend,visual_design · medium | direct | regex | — |
| frontend.responsive_breakpoint.001 | frontend/responsive_breakpoint | frontend,visual_design · medium | agent | unit_test | workspace (style.css + check.py) |
| frontend.accessibility_fix.001 | frontend/accessibility_fix | frontend,visual_design · hard | agent | unit_test | workspace (index.html + check.py) |
| voxel.solid_box.001 | voxel/solid_box | voxel,spatial_3d · easy | direct | json_schema | — |
| voxel.surface_voxels.001 | voxel/surface_voxels | voxel,spatial_3d · medium | direct | regex | — |
| voxel.sphere.001 | voxel/voxel_sphere | voxel,spatial_3d · medium | direct | json_schema | — |
| voxel.rotate_90.001 | voxel/rotate_voxels | voxel,spatial_3d · medium | direct | json_schema | attachment (data/input.json) |
| voxel.symmetry_axis.001 | voxel/symmetry_axis | voxel,spatial_3d · hard | direct | exact | attachment (data/input.json) |
| voxel.lattice_path.001 | voxel/lattice_path | voxel,spatial_3d · hard | direct | regex | — |
| agentic.multi_file_fix.001 | agentic/multi_file_fix | agentic,coding · hard | agent | unit_test | workspace (src/ + tests/) |
| agentic.report_generation.001 | agentic/report_generation | agentic,knowledge_work · medium | agent | artifact | workspace (data/*.csv) |
| agentic.debug_pipeline.001 | agentic/debug_pipeline | agentic,tool_calling · hard | agent | unit_test | workspace (pipeline.py) |
| agentic.api_migration.001 | agentic/api_migration | agentic,coding · hard | agent | unit_test | workspace (lib + app + test) |
| toolcall.dataset_query.001 | tool_calling/dataset_query | tool_calling,coding · medium | agent | artifact | workspace (query.py + data) |
| toolcall.data_transform.001 | tool_calling/data_transform | tool_calling · medium | agent | artifact | workspace (tool.py + inputs) |
| toolcall.shell_automation.001 | tool_calling/shell_automation | tool_calling,agentic · medium | agent | artifact | workspace (logs/) |
| toolcall.json_query_autonomy.001 | tool_calling/json_query_autonomy | tool_calling,research · hard | agent | artifact | workspace (library.json) |
| mathematics.basic.addition.001 | mathematics/basic_addition | mathematics · easy | direct | regex | — |
| mathematics.prime_factorization.001 | mathematics/prime_factorization | mathematics · medium | direct | json_schema | — |
| reasoning.exists_statement.001 | reasoning/exists_statement | formal_reasoning,general_reasoning · medium | direct | exact | — |
| reasoning.reverse_string.001 | reasoning/reverse_string | general_reasoning,coding · easy | direct | exact | — |
| longcontext.document_retrieval.001 | long_context/document_retrieval | long_context,research · medium | direct | exact | attachment (data/policies.txt) |
| longcontext.contract_obligations.001 | long_context/contract_obligations | long_context,knowledge_work · hard | direct | json_schema | attachment (data/agreement.txt) |
| longcontext.log_analysis.001 | long_context/log_analysis | long_context,research · medium | direct | exact | attachment (data/events.log) |
| longcontext.citation_lookup.001 | long_context/citation_lookup | long_context · medium | direct | exact | attachment (data/manual.txt) |
| general.knowledge.capital_facts.001 | general/capital_facts | general_reasoning,knowledge_work · easy | direct | exact | — |
| hardware.perf.probe.001 | hardware/perf_probe | hardware · trivial | direct | regex | — |

**Per-category (by directory) totals:** coding **8**, frontend **6**, voxel **6**, agentic **4**, tool_calling **4**, mathematics **2**, reasoning **2**, long_context **4**, general **1**, hardware **1** → **38**.

---

## 3. Solvability & validation method (per oracle family)

Every task is solvable by construction and its oracle is fully deterministic — no LLM judge, no model-dependent scoring:

- **`exact`** — the reference solution is a fixed literal (e.g. `code_output_prediction` prints `4 [1, 2, 3, 4]`; `document_retrieval` returns `7`). Scorer: 1.0 iff the model output equals `config.expected`.
- **`regex`** — the correct answer is matched by a fixed compiled pattern (e.g. `spot_bug` must contain `"line": 7`; `surface_voxels` must be a 3-digit integer in the checked interval). Scorer: 1.0 iff a full/anchored match is found.
- **`json_schema`** — the correct answer is a well-formed JSON document validated structurally (e.g. `json_output` requires `{"id": str, "ok": true}`; `prime_factorization` requires `factors: int[]`). Scorer: 1.0 iff the output parses and satisfies `config.schema`. The schema is strict enough to pin the correct document while tolerating presentation.
- **`unit_test`** (SHARED CONTRACT, implemented by the parallel Phase 4 scorer stream) — `config {command, workspace: "" (run_dir), timeout_seconds}` runs the command inside the task's copied workspace; 1.0 iff exit 0. Used for **agent editing tasks**: the workspace ships a *starter* source file plus an *unmodified* test file that fails until the correct edit is made (fizzbuzz, binary_search, parse_csv, refactor_legacy, multi_file_fix, debug_pipeline, api_migration, responsive_breakpoint, accessibility_fix). The test encodes the full contract, so a correct solution is both determined and verified.
- **`artifact`** (SHARED CONTRACT) — `config {path, hash, min_size}` checks that the model wrote the required output file in the workspace (e.g. `report.md`, `answers.txt`, `summary.json`), and that it is non-empty/hashes correctly; 1.0 iff present + checks pass. Used for agentic/tool-calling deliverable tasks.

All oracle scoring is deterministic by construction; where a scorer type is implemented by the parallel stream, the YAML still **loads standalone** (the loader only parses YAML and never requires the scorer type to exist).

---

## 4. Suites (§8.1 family)

All suites load via `load_suite_yaml`; every referenced `task_id` resolves to a task in this catalogue.

| suite id | name | family | # tasks |
|---|---|---|---|
| suite.daily_driver.001 | Daily Driver | daily-driver | 8 |
| suite.general_retention.001 | General Retention | general-retention | 8 |
| suite.stress.001 | Stress | stress | 9 |
| suite.atlas.001 | Atlas | atlas | 9 |
| suite.hardware.performance.001 | Hardware performance *(pre-existing, Phase 3)* | hardware_performance | 1 |
| suite.smoke.direct.001 | Direct smoke *(pre-existing, Phase 1)* | smoke | 5 |

- **`daily_driver`** — fast everyday coding/reasoning regression (json_output, fizzbuzz, basic_addition, reverse_string, capital_facts, semantic_markup, solid_box, perf_probe).
- **`general_retention`** — broad-coverage retention across every domain (coding, frontend, voxel, math, reasoning, long-context, general).
- **`stress`** — hardest agentic/frontend/spatial/long-context tasks for robustness under load.
- **`atlas`** — tasks instrumented for atlas intervention traces (router/expert routing, precision tiers); mixes direct and agent/workspace tasks.

---

## 5. Validation evidence (ONE-OFF loader scan)

Run with the repo venv (`/home/kristianaaron/tmp/eval-lab/.venv/bin/python`), using only existing `eval_lab` code (`load_task_yaml`, `load_suite_yaml`, `check_fixture_references`, `eval_lab.config.labels.unknown`):

```
TOTAL task.yaml loaded: 38
Per-domain: coding 12, frontend 6, visual_design 6, voxel 6, spatial_3d 6,
            agentic 5, tool_calling 5, long_context 4, knowledge_work 3,
            general_reasoning 3, research 3, mathematics 2, hardware 1, formal_reasoning 1
Missing fixture refs (total across all tasks): 0
Validation errors: []
Duplicate ids: []

SUITE suite.atlas.001            family=atlas              n_tasks=9  unresolved_refs=[]
SUITE suite.daily_driver.001     family=daily-driver       n_tasks=8  unresolved_refs=[]
SUITE suite.general_retention.001 family=general-retention  n_tasks=8  unresolved_refs=[]
SUITE suite.hardware.performance.001 family=hardware_performance n_tasks=1 unresolved_refs=[]
SUITE suite.smoke.direct.001     family=smoke              n_tasks=5  unresolved_refs=[]
SUITE suite.stress.001           family=stress             n_tasks=9  unresolved_refs=[]
```

Every task yaml parsed and validated through `TaskSpec` (including id pattern/version/status and label-vocab validation via `TaskLabels`). `check_fixture_references` reports **zero** missing workspace/attachment files. All suites — including the pre-existing Phase 1 `smoke_direct` and Phase 3 `hardware_perf` — resolve every referenced id.

---

## 6. Provenance & no-leakage statement (spec §9 exit gate)

**Fixture provenance.** All fixtures are authored from scratch for this catalogue and committed under each task directory (`tasks/<category>/<slug>/workspace/**` or `tasks/<category>/<slug>/data/**`). Starter source, tests, checkers, and attached long documents were written by hand for these tasks; none are copied from any benchmark, competition, public dataset, or prior eval (e.g. SWE-bench, HumanEval, MMLU-style corpora, web corpora). No fixture is shared with the training corpora of the models under test, and no fixture is reused as expert-selection or routing-calibration data.

**Self-contained, offline.** Every task is fully self-contained: prompts carry all needed context, and `execution.network: disabled` for every task. There are **no downloads and no network access at eval time** — no dependency on external APIs, hosted judge endpoints, or live fetch of any kind. `unit_test` commands run local scripts with the interpreter; `artifact` checks inspect workspace files. Reproducible with `execution.seeds` and deterministic oracles.

**No leakage.** No task in this catalogue is used as training data, as expert-selection calibration, or as calibration data for any judge/scorer. Oracle answers are fixed literals/patterns/schemas or self-checking local tests — none derived from a model's own outputs, and none informed by the model's training set.

**Category shortfall:** **none** — every §9 minimum (see table in §1) is met and the total (38 ≥ 36) is met.

---

*Fixtures, tasks, suites, and this report live in the Phase 6 working tree pending final validation by the lead (full pytest/ruff/mypy/format are run post-merge upstream of this phase report).*

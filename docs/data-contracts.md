# Data Contracts — eval-lab (Phase 0)

All persisted objects are Pydantic models with `extra="forbid"` and carry a
`schema_version` field (currently `"1.0"`). A schema version bump must accompany
any incompatible field/behavior change; old results are never silently
reinterpreted under a new schema.

## Schema index

Defined in `src/eval_lab/schemas/models.py`:

- `SCHEMA_VERSION` — `"1.0"`
- `TaskSpec`, `SuiteSpec`
- `ModelConfig`, `HarnessConfig`
- `RunManifest`
- `ScoreResult`, `TraceEvent`

## TaskSpec

```yaml
schema_version: "1.0"
id: mathematics.basic.addition.001   # dotted: domain.category.slug.nn
name: Two-number addition
description: Given two integers, return their exact sum.
version: 1                          # task revision; changes must bump
level: model | system
status: active | draft | deprecated

labels:
  domains: [mathematics]            # controlled vocab (see label ontology)
  capabilities: [mathematical_reasoning]
  modalities: [text]
  difficulty: easy
  trajectory_stages: []
  failure_modes_targeted: []
  intervention: []
  atlas_labels: []

input:
  instruction_file: prompt.md
  attachments: []
  workspace_fixture: null           # optional path validated against disk
  initial_state_hash: null

execution:
  runner: direct | agent
  sandbox: null
  image: null
  network: disabled
  timeout_seconds: 60
  seeds: [0]

oracle:
  - type: exact                     # scorer type reference
    weight: 1.0
    required: true

repetitions:
  default: 1
  seeds: [0]
```

Validation invariants:

- `id` must match `^[a-z0-9]+(\.[a-z0-9_-]+)+$`.
- `labels.*` values must belong to the label registry; unknown values raise.
- `workspace_fixture` and `attachments` are checked against a base directory by
  the loader (`check_fixture_references`).
- Unknown top-level or nested fields are rejected.

## Label ontology

Registry in `src/eval_lab/config/labels.py` (`LABEL_SCHEMA_VERSION = "1.0"`).
Vocabularies:

- `domain`, `capability`, `modality`, `difficulty`, `level`,
  `failure_mode`, `intervention`, `trajectory_stage`

Aliases (e.g. `sw-eng` → `software_engineering`, case/separator-insensitive)
are resolved to canonical spellings by `labels.validate` / `validate_many`.

## SuiteSpec

```yaml
schema_version: "1.0"
id: suite.smoke.001
name: Smoke
description: ""
version: 1
family: smoke                  # optional
tasks:
  - task_id: mathematics.basic.addition.001
    weight: 1.0
    repetitions: null          # optional override
```

## ModelConfig (spec 6.2)

```yaml
schema_version: "1.0"
id: deepseek-v4-flash-nvfp4-vllm     # dashed id
provider_type: openai_compatible
endpoint: http://localhost:8000/v1
model_name: deepseek-v4-flash
checkpoint: { source: local, path: ..., revision: null }
quantization: { format: nvfp4, details: vendor_checkpoint }
runtime: { name: vllm, version: ..., arguments: {...} }
sampling_defaults: { temperature: 0.0, top_p: 1.0, max_tokens: 4096 }
capabilities: { chat: true, images: false, tools: true }
```

## HarnessConfig (spec 6.3)

```yaml
schema_version: "1.0"
id: local-shell-agent-v1   # dashed id
agent_loop: react_tool_feedback
system_prompt_file: null
workspace_policy: isolated_copy
context_policy:
  strategy: rolling_summary_plus_recent
  max_context_tokens: null
  retain_tool_outputs: selective
recovery_policy:
  max_retries_per_tool: 0
  require_error_inspection: false
completion_contract:
  require_final_summary: false
  require_verification_evidence: false
tool_adapter_version: "1.0.0"
```

## RunManifest (spec 6.4)

Constrains timestamps to UTC (`datetime.now(UTC)`). Fields cover every aspect of
evaluated-system identity so a single run is fully reproducible.

## ScoreResult (spec 13.1)

```json
{
  "scorer_id": "unit-tests-v1",
  "score": 0.85,
  "passed": false,
  "confidence": 1.0,
  "required": true,
  "details": {},
  "evidence_artifacts": [],
  "error": null
}
```

`required=true` may force task failure independent of the weighted mean.

## TraceEvent (spec 6.5)

Append-only, monotonic `sequence`, monotonic clock `time_monotonic_ns`, optional
span/parent-span ids, and a free-form `payload`. Event types are extended in
later phases (model request, tool result, validation, telemetry sample, ...).

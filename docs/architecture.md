# Architecture — eval-lab (Phase 0)

## Purpose

eval-lab is an agent-agnostic evaluation operating layer for local language
models and complete model-plus-agent systems. It must answer which configuration
(model checkpoint, quantization, runtime, sampling, harness, context policy,
code revision) performs best on real local workloads, and which capabilities
regress after compression or runtime changes.

## Design principles (spec 4)

- **Oracle first** — deterministic oracles outrank model judges.
- **Labels are first-class** — controlled vocabularies, not free text.
- **Trace what's needed** — reproducible runs, no secret or bulk tensor storage.
- **Separate capability from efficiency** — report dimensions independently.
- **Harness effects are explicit** — same checkpoint under two agent loops is
  two evaluated systems.
- **Small gold set before scale** — quality over quantity up front.

## Evaluated system identity

A result is never attributed to a model alone. A **RunManifest** must capture:
task + suite identity/version, model + checkpoint + quantization, runtime and
launch args, harness config, hardware topology, env lock hash, seed, sampling,
budgets, warm/cold state, repetition index, and result status. Model identity
and harness identity are separate first-class objects (see
`docs/adr/0001-model-and-harness-identity.md`).

## Module map (Phase 0 subset)

| Path | Responsibility |
|------|----------------|
| `src/eval_lab/schemas/models.py` | Versioned Pydantic data contracts |
| `src/eval_lab/config/labels.py` | Controlled label vocabularies + validation |
| `src/eval_lab/tasks/loader.py` | YAML task/suite loading + fixture checks |
| `src/eval_lab/adapters/mock.py` | Deterministic offline model adapter |
| `src/eval_lab/cli/main.py` | Typer CLI (`doctor`, `validate`, `list`) |
| `tasks/` | Task YAML catalogue |
| `tests/` | Unit / integration / golden / smoke |
| `runs/` | Run output workspace |

Phase 0 deliberately ships **no** runners, tools, sandboxes, telemetry, judges,
scorers (only schema types), storage, or UI. Those arrive with their own phases.

## Object model

- `TaskSpec` — one task (inputs, execution budget, oracle scorer refs, labels).
- `SuiteSpec` — ordered references to tasks with weights/repetitions.
- `ModelConfig` — endpoint + checkpoint + quantization + runtime + sampling.
- `HarnessConfig` — agent loop, context/recovery/completion policy.
- `RunManifest` — full evaluated-system identity for one run.
- `ScoreResult` — one scorer's result; required failures may gate the task.
- `TraceEvent` — append-only event with monotonic sequence (spec 6.5).

## Validation & strictness

- `extra="forbid"` everywhere: unknown required fields are rejected.
- `schema_version` is persisted on every object.
- Labels are validated against the registry; unknown labels raise `LabelError`.
- Duplicate/unknown fixture references are surfaced by the loader and CLI.
- Enums are `StrEnum`; ids follow strict dotted or dashed patterns.

## CLI exit-code contract

| Condition | Exit code |
|-----------|-----------|
| Healthy / valid / success | 0 |
| Invalid task/suite, missing file, failed doctor | 1 |
| Unknown subcommand kind | 2 |

## Future phases (not built here)

Phase 1 direct runner → Phase 2 agent loop/sandbox → Phase 3 telemetry →
Phase 4 scorers/judge cal → Phase 5 suites/compare → Phase 6 task catalogue →
Phase 7 local-model integration → Phase 8 atlas/intervention traces.

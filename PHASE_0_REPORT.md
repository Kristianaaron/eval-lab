# PHASE_0_REPORT — eval-lab scaffold

**Status:** COMPLETE  
**Date:** 2026-07-31  
**Host:** eval-node (Linux aarch64)  
**Scope:** Phase 0 only (spec §26). No real model calls, no Docker/tools/
telemetry/judges/UI/benchmark imports. Stopped at the Phase 0 gate; not
proceeding to Phase 1 automatically.

---

## 1. What was built

Repository scaffold at `/home/kristianaaron/tmp/eval-lab`:

| Deliverable | Location |
|-------------|----------|
| Package + packaging | `pyproject.toml` (Python 3.12, hatchling, `eval-lab` entry point), `src/eval_lab/` |
| Versioned Pydantic schemas | `src/eval_lab/schemas/models.py` — TaskSpec, SuiteSpec, ModelConfig, HarnessConfig, RunManifest, ScoreResult, TraceEvent (all `schema_version="1.0"`, `extra="forbid"`) |
| Label registry + validation | `src/eval_lab/config/labels.py` — domains/capabilities/modalities/difficulty/level/failure_mode/intervention/trajectory_stage, aliases |
| Task YAML loader | `src/eval_lab/tasks/loader.py` — task+suite load, validation, fixture-reference checks |
| CLI | `src/eval_lab/cli/main.py` — `doctor`, `validate task\|suite`, `list tasks`; `--json`; exit codes 0/1/2 |
| Deterministic mock adapter | `src/eval_lab/adapters/mock.py` |
| Example tasks (3 direct) | `tasks/mathematics|reasoning|general/*.yaml` + `prompt.md` |
| Invalid-task fixtures (2) | `tests/unit/fixtures/unknown_label.yaml`, `broken_fixture.yaml` |
| Unit tests | `tests/unit/test_phase0.py` (23 tests) |
| Docs | `docs/architecture.md`, `docs/data-contracts.md`, `docs/adr/0001-model-and-harness-identity.md` |
| Repo essentials | `README.md`, `LICENSE` (Apache-2.0), `CHANGELOG.md`, `Makefile`, `.env.example`, `.gitignore` |

## 2. Commands run

```bash
uv venv .venv
uv pip install -e ".[dev]"
.venv/bin/pytest -q
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/mypy src
.venv/bin/eval-lab doctor
.venv/bin/eval-lab validate task tasks/mathematics/basic_addition.yaml
.venv/bin/eval-lab validate suite <suite>.yaml
.venv/bin/eval-lab list --dir tasks
```

Environment: Python 3.12.3, uv 0.11.16, aarch64 Linux.

## 3. Outcomes

| Check | Result |
|-------|--------|
| `uv pip install -e ".[dev]"` | clean (pydantic 2.13.4, typer 0.27.0, pyyaml 6.0.3, ruff 0.16.1, mypy, pytest 8.4.2) |
| `pytest -q` | **23 passed** |
| `ruff check` | All checks passed |
| `ruff format --check` | 12 files already formatted |
| `mypy src` (strict) | Success: no issues found in 11 source files |
| `eval-lab doctor` (exit 0) | [ok] import, [ok] mock_adapter, [ok] schema_roundtrip |
| `eval-lab doctor --json` | valid JSON, `{"status":"ok"}` |
| `eval-lab validate task` (valid) | exit 0 |
| `eval-lab validate task` (unknown label) | exit 1 |
| `eval-lab validate task` (broken fixture) | exit 1 |
| `eval-lab validate suite` (valid) | exit 0 |
| `eval-lab validate frob` (unknown kind) | exit 2 |
| `eval-lab list --dir tasks` | found 3 task(s): addition, reverse_string, capital_facts |

## 4. Exit-gate evidence (§26)

- **Package installs cleanly** — `uv pip install -e .[dev]` succeeded; `eval-lab`
  entry point resolves.
- **Lint/type checks pass** — ruff (lint+format) and mypy strict both clean.
- **Schemas round-trip** — `doctor` schema_roundtrip check ok; test
  `test_all_core_schemas_roundtrip` covers all seven schemas.
- **CLI help works** — `eval-lab --help` and per-command `--help` render;
  exit codes verified (0/1/2).
- **No real model required** — deterministic mock adapter drives `doctor` and
  tests; mock output byte-identical across repeated identical prompts
  (`test_mock_adapter_is_deterministic`).

## 5. Test coverage (spec 26 #10 → spec 21.1)

- schema round-tripping — `test_task_spec_roundtrip`,
  `test_all_core_schemas_roundtrip`
- unknown fields rejected — `test_rejects_unknown_fields`
- invalid id pattern — `test_rejects_invalid_id_pattern`
- duplicate/unknown labels — `test_label_validate_unknown_raises`,
  `test_label_unknown_reports_bad`, `test_unknown_label_task_fails_validation`
- broken fixture paths — `test_broken_fixture_detected`
- CLI exit codes — `test_cli_doctor_ok/json`, `test_cli_validate_*`,
  `test_cli_list_tasks_json`

(Explicit duplicate-ID detection across a directory scan is deferred to Phase 1,
which owns the task registry; the loader rejects invalid ids and the schema
enforces uniqueness per object.)

## 6. Unresolved decisions / notes

- **Duplicate-task-ID detection** across the `tasks/` tree is not enforced by a
  single CLI command in Phase 0 (no registry command was in the Phase 0
  deliverable list). Phase 1's registry will own it.
- **`instruction_file` existence** is not verified at validate time (only
  `workspace_fixture`/`attachments` are disk-checked, per the Phase 0 loader
  scope). Prompt files for the 3 example tasks exist but the check itself is a
  Phase 1 concern.
- Label canonicalization resolves case and `_`/`-` separators to canonical
  spellings; unknown canonical forms raise.
- Repo lives at `/home/kristianaaron/tmp/eval-lab`; not yet pushed to a remote.

## 7. Blocking requirements for Phase 1

Before Phase 1: task registry with duplicate-id/instruction-file validation,
direct runner, OpenAI-compatible adapter, deterministic scorers
(exact/regex/json), JSONL+SQLite persistence, Markdown run report, and
end-to-end runs of ≥5 direct tasks per the §10.5 repetition policy.

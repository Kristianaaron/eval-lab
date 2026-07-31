# Changelog

All notable changes to eval-lab are documented here. Format: Keep a Changelog.

## [0.1.0] - 2026-07-31

Phase 0 scaffold:

- Versioned Pydantic schemas: TaskSpec, SuiteSpec, ModelConfig, HarnessConfig,
  RunManifest, ScoreResult, TraceEvent.
- Controlled label registry with validation and aliases.
- YAML task/suite loader with fixture-reference checks.
- CLI: `doctor`, `validate task|suite`, `list tasks` (JSON output, exit codes).
- Deterministic mock model adapter.
- Packaging (uv/hatchling), Ruff, mypy, pytest.
- Docs: architecture, data-contracts, ADR-0001.

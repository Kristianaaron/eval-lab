VENV ?= .venv
PY ?= $(VENV)/bin/python
PIP ?= $(VENV)/bin/pip

.PHONY: install dev test lint format check doctor help

install:
	uv venv $(VENV)
	uv pip install -e .

dev:
	uv venv $(VENV)
	uv pip install -e ".[dev]"

test:
	$(PY) -m pytest

lint:
	$(VENV)/bin/ruff check src tests

format:
	$(VENV)/bin/ruff format src tests
	$(VENV)/bin/ruff check --fix src tests

check: lint
	$(VENV)/bin/mypy src
	$(VENV)/bin/ruff format --check src tests

doctor:
	$(VENV)/bin/eval-lab doctor

help:
	@echo "targets: install dev test lint format check doctor"

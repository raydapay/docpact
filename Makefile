.PHONY: help install format format-check lint lint-check typecheck test coverage verify docs docs-check dogfood

# Default target
help:
	@echo "Developer targets:"
	@echo "  make install        Install all dependencies (uv sync)"
	@echo "  make format         Format codebase using ruff (writes changes)"
	@echo "  make format-check   ruff format --check (no writes; CI gate)"
	@echo "  make lint           Run ruff linter and auto-fix violations"
	@echo "  make lint-check     Run ruff linter without auto-fix (CI gate)"
	@echo "  make typecheck      Run static type analysis using ty"
	@echo "  make test           Run pytest (fast, no coverage)"
	@echo "  make coverage       Run pytest with coverage (fail_under=85)"
	@echo "  make verify         Full pipeline: format → lint → typecheck → coverage → dogfood"
	@echo "  make docs           Generate docs/rules/*.md from the rule registry"
	@echo "  make docs-check     Verify docs/rules/*.md matches registry (CI gate)"
	@echo "  make dogfood        Run docpact on its own source (self-check)"

install:
	uv sync

format:
	uv run ruff format src/ tests/

format-check:
	uv run ruff format --check src/ tests/

lint:
	uv run ruff check --fix src/ tests/

lint-check:
	uv run ruff check src/ tests/

typecheck:
	uv run ty check src/

test:
	uv run pytest

coverage:
	uv run coverage run -m pytest
	uv run coverage report -m

docs:
	uv run python scripts/generate_rule_docs.py

docs-check:
	uv run python scripts/generate_rule_docs.py
	git diff --exit-code docs/rules/

dogfood:
	uv run docpact check src/

verify:
	@echo "Starting full verification pipeline..."
	@($(MAKE) format && \
	  $(MAKE) lint && \
	  $(MAKE) typecheck && \
	  $(MAKE) coverage && \
	  $(MAKE) dogfood && \
	  echo "Verification successful.") || \
	 (echo "Verification failed."; exit 1)

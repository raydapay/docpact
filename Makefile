.PHONY: help install format format-check lint lint-check typecheck test coverage verify verify-ci docs docs-check stats-update stats-check dogfood bench bench-update release

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
	@echo "  make verify         Full pipeline (auto-fix): format → lint → typecheck → coverage → docs-check → dogfood"
	@echo "  make verify-ci      Same pipeline, non-mutating (check-only + git diff guard); used in CI and release"
	@echo "  make docs           Generate docs/rules/*.md from the rule registry"
	@echo "  make docs-check     Verify docs/rules/*.md matches registry (CI gate)"
	@echo "  make stats-update   Sync README.md test count and coverage (writes)"
	@echo "  make stats-check    Verify README.md stats match current suite (CI gate)"
	@echo "  make dogfood        Run docpact on its own source (self-check)"
	@echo "  make bench          Run throughput benchmark and compare against baseline"
	@echo "  make bench-update   Run benchmark and save result as new baseline"
	@echo "  make release        Cut a release: make release VERSION=x.y.z"

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
	@if [ -n "$$(git status --short docs/rules/)" ]; then \
	  echo "docs/rules/ is out of sync with the registry:"; \
	  git status --short docs/rules/; \
	  exit 1; \
	fi

stats-update:
	uv run python scripts/update_readme_stats.py

stats-check:
	uv run python scripts/update_readme_stats.py --check

dogfood:
	uv run docpact check src/

bench:
	uv run python scripts/bench.py

bench-update:
	uv run python scripts/bench.py --update

release:
	@test -n "$(VERSION)" || (echo "usage: make release VERSION=x.y.z"; exit 1)
	@git diff --quiet && git diff --cached --quiet || (echo "error: working tree is not clean"; exit 1)
	$(MAKE) verify
	uvx bump-my-version bump --new-version $(VERSION) --no-commit --no-tag --allow-dirty
	uvx git-cliff --tag v$(VERSION) --output CHANGELOG.md
	git add pyproject.toml README.md docs/spec/docpact-spec.md CHANGELOG.md
	git commit -m "chore: release v$(VERSION)"
	git tag -a "v$(VERSION)" -m "v$(VERSION)"
	@echo ""
	@echo "Release v$(VERSION) tagged. Run: git push --follow-tags"

verify:
	@echo "Starting full verification pipeline..."
	@($(MAKE) format && \
	  $(MAKE) lint && \
	  $(MAKE) typecheck && \
	  $(MAKE) coverage && \
	  $(MAKE) stats-update && \
	  $(MAKE) docs-check && \
	  $(MAKE) dogfood && \
	  echo "Verification successful.") || \
	 (echo "Verification failed."; exit 1)

verify-ci:
	@echo "Starting CI verification pipeline (non-mutating)..."
	@($(MAKE) format-check && \
	  $(MAKE) lint-check && \
	  $(MAKE) typecheck && \
	  $(MAKE) coverage && \
	  $(MAKE) stats-check && \
	  $(MAKE) docs-check && \
	  $(MAKE) dogfood && \
	  git diff --exit-code && \
	  echo "Verification successful.") || \
	 (echo "Verification failed."; exit 1)

# Changelog

Generated from conventional commits. Only `feat:` and `fix:` entries appear.
## [0.1.0a10] — 2026-05-31

### Fixed
- **sem:** Harden SEM001 prompt against substantive-Returns false positives (#11)


## [0.1.0a9] — 2026-05-31

### Added
- **bench:** Add --crossfile to measure the cross-file pre-pass cost
- **bench:** Break down cross-file pre-pass into startup vs query time


### Fixed
- **crossfile:** Resolve file:// URIs correctly on Windows


## [0.1.0a8] — 2026-05-31

### Added
- **lsp:** Add provider-agnostic LSP client + config (Step 1)
- **reg:** Capture input_model ref + description Args keys (Step 2)
- **reg:** Add REG010 cross-file Args/input-model parity (Step 3)
- **crossfile:** Imported-handler Tier-3 floor + semantic composition (ADR-010 increment 1)
- **reg:** Add REG011 cross-file handler-signature parity (ADR-010 increment 2)


## [0.1.0a7] — 2026-05-30

### Added
- **cli:** Opt-in parallel analysis (--jobs) and docpact bench
- **semantic:** Open the SEM layer — docpact semantic + pluggable LLM backend


### Fixed
- **cli:** Guard resource access for Windows typecheck
- Register DOC052 — shipped but never loaded


## [0.1.0a6] — 2026-05-30

### Added
- **parser:** Extract same-file tool-registry entries
- **rules:** Add REG001/REG002 tool-registry consistency rules
- **tiers:** Apply Tier 3 floor from tool-registry membership
- **cli:** Wire tool-registry detection and registry config


### Fixed
- Drop unused ty:ignore directive in DOC052
- **release:** Relock uv.lock on version bump


## [0.1.0a4] — 2026-05-21

### Added
- **cli:** Add --show-files, --exit-non-zero-on-fix, --error-on-warning
- Add DOC052 — require Examples section at configurable tier threshold


### Fixed
- Pre-PyPI review fixes — docs, coverage, invariants, perf
- Use as_posix() for fnmatch path comparisons
- Windows compatibility — path separators and line endings
- Explicit utf-8 encoding in generate_rule_docs.py for Windows


## [0.1.0a3] — 2026-05-20

### Added
- Add FIX004 — detect suppression not on def keyword line
- Auto-sync README test count and coverage via stats-update/stats-check


### Fixed
- Clean up CHANGELOG a1, mark DOC098 reserved in registry


## [0.1.0a2] — 2026-05-20

### Fixed
- Explicit utf-8 encoding on all read_text/write_text calls
- **ci:** Non-mutating verify-ci gate for CI and release pipeline


## [0.1.0a1] — 2026-05-19

### Added
- Phase 1 — parser/source, parser/docstring, tooling
- Phase 2 — tier assignment and rule registry
- Phase 6 — JSON output and inline suppression
- Phase 7 — remaining rules (DOC012-DOC099, MCP001, FIX001)
- Phase 8 — generate, show-schema, list-rules commands
- Phase 9 — docpact.testing programmatic assertions API
- Phase 10 — pre-commit hook, rule docs, dogfooding
- **suppress:** Introduce # nodo suppression syntax with configurable markers
- **rules:** Add DOC002 module-level docstring enforcement
- **rules:** Add FIX002 — suppression without -- reason
- **rules:** Add DOC003 — missing class-level docstring
- **rules:** Implement DOC050 — Pydantic field missing description
- **parser:** Add NumPy docstring parser
- SARIF output, TY rules, review fixes
- **bench:** Add throughput benchmark with regression guard
- Add --add-suppression baselining and rename tiers config key
- Add --changed-only <ref> to check command
- __all__ awareness in tier assignment
- Function-level tier pragma (# docpact: tier=N)
- DOC021 — "Defaults to X" drift in Args prose
- Ruff/ty-inspired CLI ergonomics (v0.4 quick-wins)
- **output:** --format github for GitHub Actions annotations
- **output:** Color diagnostics + --color auto|always|never
- --output-file writes output to a file instead of stdout
- **DOC013:** Add safe fix — replace non-canonical body with 'None.'
- Round-2 external dry-run — bool norm, per-file-tier DOC003, comma CLI
- **DOC022:** Typed prose annotation mismatch
- ConfigResult, --config flag, root-anchored glob matching
- **rules:** Add PARSE001 — Python syntax error rule


### Fixed
- **doc002:** Exclude __init__.py files by default
- **DOC021:** Strip rST backticks, unwrap F(literal) defaults, literals only
- **suppress:** Use tokenize to skip string literals in suppression scan




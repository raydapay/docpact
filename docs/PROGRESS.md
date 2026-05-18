# Implementation progress

Tracks phase completion and per-module status. Update this file when a phase
ships; do not put status in CLAUDE.md.

---

## Current status

**Phase 8 complete. Phase 9 (testing API) is next.**

---

## Phase log

### Phase 1 — Parser and model ✓
Commit: `5611abf`

- `src/docpact/parser/source.py` — AST-based `FunctionInfo` extraction.
  Handles async functions, nested classes/functions, scope-aware
  `containing_class`, `bound` parameter kind, byte-offset fields,
  decorator argument capture.
- `src/docpact/parser/docstring.py` — `GoogleParser` backed by griffe.
  Recovers `Args/Raises: None.` sections griffe silently drops; extracts
  inline `Stability:` field via regex.
- `src/docpact/model/function_info.py` — added `bound` to
  `ParameterInfo.kind`; added four byte-offset fields.
- `src/docpact/model/diagnostic.py` — `Severity` uses `StrEnum`.
- Tests: 85 tests, 97% coverage on implemented modules.
- Tooling: replaced mypy with ty; added `Makefile`; `make verify` passes.

### Phase 2 — Tier assignment and rule registry ✓
Commit: `049bae8`

- `src/docpact/tiers.py` — `assign_tier` implements all 7 rules from spec
  §10.1 using fnmatch for file-path glob patterns in tier_overrides.
- `src/docpact/rules/_registry.py` — already complete in skeleton; verified
  end-to-end with stub rule imports.
- Tests: `tests/test_tiers.py` (40 tests), `tests/test_rules/test_registry.py`
  (7 tests). 132 total, all passing.

### Phase 3 — First rules ✓
Commit: `f62cfbe`

- `DOC001` missing docstring — tier-appropriate `[FILL]`-stub safe fix,
  inserts at `def_end_offset`, excludes bound receiver from Args section.
- `DOC007` param/signature mismatch — phantom params (all tiers) and
  missing required params (Tier 2+); strips `*`/`**` from griffe entry keys
  before comparison against bare `FunctionInfo.name` values.
- `src/docpact/output/__init__.py` — `format_text` (path:line:col: CODE [*]
  message, `= help:` line) and `format_summary` (Found N errors (M fixable)).
- `src/docpact/cli.py` `check` command — walks paths/dirs, assigns tier,
  runs all registered rules, sorts and emits results, exits 1 on errors.
- Tests: 174 total, 98% coverage.

### Phase 4 — Configuration ✓
Commit: `c59640d`

- `src/docpact/config.py` — `load_config()` with upward walk; parses
  `docpact.toml` or `pyproject.toml [tool.docpact]`; resolves all keys
  into a typed frozen `Config` dataclass; docpact.toml wins with warning.
  Exports `rule_is_enabled`, `file_ignores_for`, `file_is_excluded`.
- CLI `check` command now applies select/ignore, tier_overrides,
  rule_severities, per_file_ignores, and exclude patterns.
- CLI tests run in isolated_filesystem to avoid project config.
- 208 tests, 97% coverage.

### Phase 5 — Fix engine ✓
Commit: `5b86cdf`

- `src/docpact/fix.py` — `apply_fixes` (in-place, end-to-start, conflict
  detection per file, deduplication) and `diff_fixes` (unified diff,
  no write). `ConflictError` for overlapping range pairs.
- CLI: `--fix`, `--unsafe-fixes`, `--diff` all wired and tested.
- 231 tests, 96% coverage.

### Phase 6 — Output ✓
Commit: `cce438e`

- `src/docpact/output/__init__.py` — `format_json` with versioned envelope
  `{"version":"1", "diagnostics":[...], "summary":{...}}`; each diagnostic
  includes fixable/unsafe_fixable flags and cwd-relativised path.
- `src/docpact/suppress.py` — `parse_suppressions`, `is_suppressed`,
  `apply_suppressions`; bare `# noqa` suppresses all codes; filters after
  rules run and before output/exit-code evaluation.
- CLI: `--format json` wired; `_run_checks` returns per-file suppression
  maps; `visible` filtered list used for output and exit code.
- 273 tests, 97% coverage.

### Phase 7 — Remaining rules ✓
Commit: `394e0c5`

- `DOC012`: required section missing for tier (Args, Returns, Raises,
  Constraints, Stability, MCP). Fires when docstring present but section
  absent; canonical `None.` sections satisfy the check.
- `DOC013`: non-canonical empty section (N/A, None without period, blank
  body). Warning. Detection only; byte-range fix deferred.
- `DOC014`: suspected parameter typo via difflib similarity ≥ 0.6.
  Warning, no fix (intent ambiguous).
- `DOC051`: Constraints section duplicates Annotated metadata. Heuristic:
  numeric values from MaxLen/MinLen/Ge/Le/etc. matched against prose.
- `DOC099`: unfilled `[FILL]` stub marker.
- `MCP001`: both decorator `description=` and docstring `MCP:` section
  present. Detection only; section-removal fix deferred.
- `FIX001`: bare `# noqa` without specific codes. Line-level rule wired
  into `_run_checks` via `check_bare_noqa`.
- `DOC050`, `DOC098`: registered stubs. DOC050 needs class-level analysis
  (Phase 8). DOC098 needs `--doctest` flag.
- 361 tests, 97% coverage.

### Phase 8 — Supporting commands ✓
Commit: `a6da41f`

- `generate`: inserts `[FILL]`-stub docstrings for undocumented functions.
  Reuses DOC001 fix objects; respects `# noqa: DOC001` suppressions and
  config exclude. `--diff` shows unified diff without writing.
- `show-schema --tier N`: prints required/recommended/optional sections
  for the given tier in human-readable form.
- `list-rules [--format json]`: aligned table or JSON array of all
  registered rules with code, namespace, severity, fixability, summary.
- 380 tests, 97% coverage.

### Phase 9 — Testing API
Status: **not started**

- `docpact.testing` public functions.

### Phase 10 — Polish
Status: **not started**

- Pre-commit hook configuration.
- Documentation page generation per rule code.
- Self-application (dogfooding) on docpact's own source.

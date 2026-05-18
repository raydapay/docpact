# Implementation progress

Tracks phase completion and per-module status. Update this file when a phase
ships; do not put status in CLAUDE.md.

---

## Current status

**v0.1 complete. Codebase is self-hosting.**

Active: maintenance, v0.2 planning. See "Recent changes" and "v0.2 scope" below.

---

## Recent changes (post-v0.1)

### DOC002 — module-level docstring enforcement — 2026-05-18

- `DOC002` fires at WARNING severity when a Python file has no module-level docstring.
- Wired as a file-level rule (same pattern as FIX001 — `check_module_docstring` called
  directly from `_run_checks`, not through the function-level loop).
- Empty files and files with syntax errors are silently skipped.
- Default severity: WARNING (weaker than DOC001's ERROR; module docstrings are more
  often legitimately absent in namespace packages and generated files).
- Disable for specific files via `[tool.docpact.per-file-ignores]`.

### suppress_comment / # nodo — 2026-05-18

Commits: `db3ae18`, `4c5c8f1`

- Introduced `# nodo: CODE` as docpact's own suppression syntax.
  Replaces `# noqa: CODE` to eliminate conflict with ruff's RUF100, which
  silently strips unknown `# noqa` codes from source files on auto-fix.
- Configurable via `suppress_comment = ["nodo"]` in `[tool.docpact]`. Accepts
  a list — `["nodo", "noqa"]` matches both during a migration period.
- `ruff external = [...]` removed from the project's own `pyproject.toml`.
- FIX001 summary and messages updated to be marker-agnostic.
- ADR-004 written to record the decision.
- **Footgun:** suppression must be on the `def` line. Placement on `) -> None:`
  looks valid but is silently ignored — `func.line` is the `def` keyword line.
  ruff's formatter moves trailing comments to `) -> None:` when it wraps
  signatures; use `def foo(  # nodo: CODE` (after the opening paren) instead.

---

## v0.2 scope (planned)

Items explicitly deferred from v0.1 (spec §5.3 and §5.4):

- **pytest plugin** — `docpact[pytest]` extra declared, plugin not implemented.
  `docpact.testing` programmatic API covers v0.1 testing needs; plugin is a
  layer on top.
- **NumPy docstring parser** — parser abstraction is in place; add the parser,
  wire it to `format = "numpy"` config.
- **Sphinx docstring parser** — lower priority than NumPy; not on roadmap yet.
- **SARIF output** — `--format sarif`. Only text and JSON in v0.1.
- **TY rules** — ty cross-validation namespace. Allocated, no rules.
- **HEUR rules** — heuristic namespace. Allocated, no rules.
- **Third-party rule plugin API** — rules are internal in v0.1.
- **Tier 4 automatic detection** — explicit config-only in v0.1.
- **Semantic mode** (`SEM` namespace) — LLM-based analysis. No code, no prompts,
  no API client. Entire subsystem absent from v0.1.
- **DOC050** (Pydantic field missing description) — registered stub; needs class-level
  analysis to associate `Field(...)` calls with the enclosing model.
- **DOC098** (doctest exception) — **explicitly out of scope, not merely deferred.**
  Executing docstring Examples sections has arbitrary side effects. There is no safe
  sandboxing strategy that does not require reimplementing a full test harness — out
  of scope for a structural linter. The rule stub remains in the registry so the code
  is reserved; the check function is permanently empty.

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
  `apply_suppressions`; bare suppression comment suppresses all codes; filters
  after rules run and before output/exit-code evaluation.
  (Note: initially used `# noqa` syntax; migrated to `# nodo` post-v0.1 — see
  "Recent changes" above.)
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
- `FIX001`: bare inline suppression comment without specific codes. Line-level
  rule wired into `_run_checks` via `check_bare_noqa`.
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

### Phase 9 — Testing API ✓
Commit: `60e40f5`

- `src/docpact/testing.py` — five public functions per spec §14.1:
  `assert_tier`, `assert_section_present`, `assert_params_match_signature`,
  `assert_mcp_schema_from_docstring`, `get_parsed_docstring`.
- Function lookup uses `__code__.co_filename` + `co_firstlineno` so the
  analyzed code is never imported — `inspect.unwrap` follows `__wrapped__`
  chains for decorated callables.
- `assert_mcp_schema_from_docstring` returns
  `{"description": str, "parameters": dict[str, str]}`; prefers MCP section
  body, falls back to summary.
- Tests: 27 tests in `tests/test_testing.py`; removed `testing.py` from
  coverage omit list (96% overall, 85% on testing module).

### Phase 10 — Polish ✓
Commit: `fbca22a`

- `.pre-commit-hooks.yaml` — standard pre-commit hook definition; exposes
  `id: docpact` for downstream consumers.
- `scripts/generate_rule_docs.py` — generates `docs/rules/<code>.md` per
  registered rule from live registry metadata. `make docs` runs it.
- Dogfooding: `uv run docpact check src/` exits 0. Fixed 50 violations across
  20 source files: summary docstrings for helper functions, Args + Returns for
  all rule `check()` functions, `# nodo: DOC012` for CLI command functions
  (args documented by click), `# nodo: DOC099` for functions that describe
  `[FILL]` markers in explanatory prose.
- `make dogfood` target added for ongoing self-check.

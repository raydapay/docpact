# Implementation progress

Tracks phase completion and per-module status. Update this file when a phase
ships; do not put status in CLAUDE.md.

---

## Current status

**Phase 3 complete. Phase 4 (configuration loading) is next.**

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

### Phase 4 — Configuration
Status: **not started**

- `src/docpact/config.py` — pyproject.toml / docpact.toml loading per spec §14.
- Wire config into rule selection and tier overrides.

### Phase 5 — Fix engine
Status: **not started**

- Apply fixes in-place; conflict detection (no overlapping ranges).
- `--fix` and `--unsafe-fixes` flags; `--diff` dry-run.

### Phase 6 — Output
Status: **not started**

- JSON output format with stable schema.
- Suppression handling (`# noqa: CODE`).

### Phase 7 — Remaining rules
Status: **not started**

- `DOC012`, `DOC013`, `DOC014`, `DOC050`, `DOC051`, `DOC098`, `DOC099`.
- `MCP001`, `FIX001`.

### Phase 8 — Supporting commands
Status: **not started**

- `generate` (stub emission).
- `show-schema` (tier requirements display).
- `list-rules`.

### Phase 9 — Testing API
Status: **not started**

- `docpact.testing` public functions.

### Phase 10 — Polish
Status: **not started**

- Pre-commit hook configuration.
- Documentation page generation per rule code.
- Self-application (dogfooding) on docpact's own source.

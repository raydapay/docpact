# Implementation progress

Tracks phase completion and per-module status. Update this file when a phase
ships; do not put status in CLAUDE.md.

---

## Current status

**v0.1 complete. v0.2 complete. v0.3 complete. Codebase is self-hosting.**

Active rules: DOC001–DOC003, DOC007, DOC012–DOC014, DOC021, DOC050,
DOC098–DOC099, MCP001, FIX001–FIX003, TY001–TY002. 720 tests, 94% coverage.
DOC051 deferred (see "Deferred with reasoning" below).

No active milestone.

---

## Recent changes (post-v0.3)

### recon-app dry-run response — 2026-05-19

Addressed 5 of 7 findings from external dry-run on a real FastAPI codebase.

**DOC021 — three fixes:**
- rST backtick stripping: `_normalize` now strips ` ``...`` ` pairs before
  quote-stripping. Fixes ` ``"human"`` ` matching `"human"`.
- Wrapper default extraction: `Query(False)`, `Field("x")` — extracts inner
  literal for comparison. Error messages still show the original expression.
- Literals-only scope: DOC021 now skips parameters whose effective default
  is not a Python constant. `SESSION_REGISTRY`, `DEFAULT_TIMEOUT`, etc. are
  excluded. Known blind spot documented in rule module docstring: a constant
  whose prose description disagrees with its actual value won't fire.

**DOC003 — class tier logic:**
- Leading underscore → silent (private by convention).
- Module defines `__all__` → only listed top-level classes fire.
- No `__all__`, no underscore → fires (assumed public).
- `__all__` does not apply to nested classes.
- Module docstring updated with migration guidance.

**FIX003 — stale suppression detection (new rule):**
- Fires when `# nodo: CODE` has no active violation for `CODE` on that line.
- Complement to `--add-suppression` baselining — mechanically identifies
  suppressions that can be safely deleted after docstrings are written.
- Implemented as a file-level post-pass in `_run_checks`; needs the complete
  violation set before suppression filtering.
- Dogfood note: 12 FIX003 warnings on docpact's own source (examples in
  module docstrings picked up by the line scanner). Pre-existing limitation
  of `parse_suppressions` not skipping string literal content.

**Deferred (inbox issues #2, #3):**
- `--config` flag for explicit pyproject.toml path.
- `per-file-tier` glob anchoring to project root.
Both pair naturally; deferred to a UX pass.

### recon-app dry-run follow-up (round 2) — 2026-05-19

Addressed 3 follow-up findings after round-1 push.

**DOC021 — boolean capitalisation:**
- `_normalize` now lowercases `True`/`False`/`None` so prose `false`/`true`/`none`
  matches Python-canonical defaults. `Query(False)` + `"Defaults to false."` no
  longer fires. Drift still fires when the value itself is wrong (e.g. `True` vs `false`).

**DOC003 — per-file-tier = 1 silences class checks:**
- `file_tier_override_for` added to `config.py` (and exported + tested).
- `_run_checks` skips DOC003 when the file's first matching `per-file-tier` pattern
  is `1`. Tier 2/3/4 and no-override files are unaffected.

**CLI — comma-separated codes:**
- `_expand_codes` splits comma-separated values in `--select`, `--ignore`,
  `--extend-select`, `--extend-ignore` before processing.
- Fixes `--select DOC021,DOC003` silently exiting 0 instead of running both rules.

### CLI ergonomics + rule maintenance — 2026-05-19

**CLI quick-wins** (ruff/ty/uv-inspired):

- **`--extend-select` / `--extend-ignore`** — additive rule selection/ignore on top
  of config, without replacing it. Useful for one-off CI overrides.
- **`--no-config`** — skip `pyproject.toml`/`docpact.toml`; use defaults. Also
  added to the `generate` command.
- **`-q / --quiet`** — suppress all output except the exit code.
- **`--statistics`** — print a per-rule violation count table after the main output
  (sorted by count desc). Sourced from `format_statistics()` in `output/__init__.py`.
- **`--color auto|always|never`** — ANSI color via rich. `auto` (default) enables
  when stdout is a TTY and no `--output-file` is set. Error codes bold red, warning
  bold yellow, fix markers bold cyan, help lines dim.
- **`--output-file PATH`** — write output to a file instead of stdout. Color is
  automatically disabled when writing to a file.
- **`--no-respect-gitignore`** — opt out of `.gitignore` filtering. The config key
  `respect_gitignore = true` (default) is the new persistent setting.
- **`.gitignore` respect** — `_filter_gitignored()` calls `git check-ignore --stdin`;
  no-ops gracefully outside a git repo.
- **Exit code 2** on config parse errors (previously crashed); wraps `ConfigError`
  as `click.UsageError`.

**Output formats:**

- **`--format github`** — emits `::error`/`::warning` GitHub Actions workflow
  annotations. `::` in messages percent-encoded; columns 1-based.

**DOC013 safe fix:**

- Replaces non-canonical empty bodies (`N/A`, `NA`, `None`, whitespace-only) with
  `"None."` in-place. Blank/None bodies get a diagnostic but no fix (no text to
  locate). Byte offset computed from `func.docstring_start_offset + 3 + UTF-8
  prefix length`.

**MCP001 — three-state logic documented, severity lowered:**

- Module docstring now explains the three states: neither → DOC012; one → OK;
  both → MCP001 WARNING. Default severity changed from ERROR to WARNING (conflict
  is a maintenance concern, not a structural error). Automated fix removed from
  design — resolving two descriptions requires human judgment.

**DOC051 — deferred to backlog:**

- Removed from active registry. Concept is sound (type-expressible constraints
  belong in `Annotated`, not prose), but the numeric-substring heuristic produces
  false positives on legitimate docstrings. Code reserved. Full rationale in
  "Deferred with reasoning" below.

---

## Recent changes (post-v0.2)

### v0.3 delivery — 2026-05-19

All four v0.3 priorities shipped in a single session.

- **`--changed-only <ref>`** on `check`: restricts checks to `.py` files that
  differ from the given git ref (`git diff --name-only <ref> -- '*.py'`),
  intersected with the normally-collected file list. Exits clearly if not in a
  git repo or if the ref is invalid.

- **`__all__` awareness in tier assignment**: `parse_all_names()` reads
  module-level `__all__` as a frozenset of string literals (returns `None` for
  absent or dynamically constructed `__all__`). New rule 3 in `assign_tier`:
  functions listed in `__all__` are Tier 2 floor; functions absent from a
  module that defines `__all__` are Tier 1 ceiling. MCP decorators and
  file-level config overrides still take priority.

- **Function-level tier pragma** (`# docpact: tier=N`): opt-in via
  `allow_pragma = true` in `[tool.docpact]`. Parsed by `parse_tier_pragma()`
  from the `def` line (same placement as `# nodo:`). Values 1–4 only.
  Applied after `assign_tier()` in `_run_checks`.

- **DOC021** — "Defaults to X" drift: fires at WARNING when an Args entry
  contains a `Defaults to <value>` phrase whose value does not match the
  signature default. Detection only; no auto-fix. String defaults are
  normalised by stripping outer quotes before comparison.

---

## Recent changes (post-v0.1)

### TY001, TY002 — type/docstring contradiction rules — 2026-05-18

New `TY` namespace for cross-validation between type annotations and docstring content.

- **TY001** (ERROR): explicit `-> None` annotation but Returns section has substantive
  content. The annotation promises nothing; the docstring contradicts it.
  Skips canonical-empty bodies ("None.", "None", "N/A") — those express absence
  explicitly and are structurally acceptable.
- **TY002** (WARNING): non-None return annotation but Returns section body is `"None."`
  (canonical empty). DOC012 is satisfied by presence alone; TY002 catches the
  coherence failure DOC012 misses.
- Both rules skip unannotated functions (contradiction is unconfirmable).
- `TY` namespace added to docpact's own `select` in `pyproject.toml`.

### SARIF output (`--format sarif`) — 2026-05-18

- `format_sarif` added to `src/docpact/output/__init__.py`.
- Produces SARIF 2.1.0: single run, `tool.driver` populated from live rule registry,
  `results` array with `ruleId`, `level`, `message`, and `physicalLocation`.
- Relative URIs with `uriBaseId = "%SRCROOT%"` when `cwd` provided; absolute
  `file://` URIs otherwise. `originalUriBaseIds` set accordingly.
- SARIF columns are 1-based; model stores 0-based — `column + 1` applied.
- `--format` choice in CLI extended to `["text", "json", "sarif"]`.

### NumPy docstring parser — 2026-05-18

- `NumpyParser` added to `src/docpact/parser/docstring.py`, backed by `griffe.parse_numpy`.
- Shared `_sections_from_griffe` helper extracted; `GoogleParser` refactored to use it.
  No behaviour change to Google parsing.
- NumPy `Parameters` → docpact `Args`; `Notes` / `Note` → `Notes`; `See Also` mapped.
- `format = "numpy"` in `[tool.docpact]` selects `NumpyParser` in `_run_checks`.
- Config validation updated: `_VALID_FORMATS = {"google", "numpy"}`.
- RST/Sphinx parser explicitly deferred: infrastructure ready, no demand yet.

### FIX002 — suppression without -- reason — 2026-05-18

- `FIX002` fires at WARNING severity when a suppression names codes but has no `-- reason`.
- Companion to FIX001. `# nodo: DOC001` fires; `# nodo: DOC001 -- reason` is clean.
- `FIX` namespace added to docpact's own `select = ["DOC", "MCP", "FIX"]` for dogfooding.

### DOC003 — class-level docstring enforcement — 2026-05-18

- `DOC003` fires at WARNING severity when any class definition has no docstring.
- Applies to top-level, nested, and inner classes.
- Unlike DOC002, no default exclusion for `__init__.py` — classes there need docs too.

### DOC050 — Pydantic field missing Field(description=...) — 2026-05-18

- Replaced long-standing stub with a real implementation.
- Detects Pydantic models via `"BaseModel" in base_name` heuristic.
- Fires for bare annotations, non-Field defaults, Field() without description=, empty description.
- Skips private fields (`_name`) and ClassVar fields.

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

## v0.2 scope

### Already shipped ✓
- **NumPy docstring parser** — `format = "numpy"` in config.
- **DOC002** — module-level docstring enforcement.
- **DOC003** — class-level docstring enforcement.
- **DOC050** — Pydantic field missing `Field(description=...)`.
- **FIX002** — suppression without `-- reason`.
- **SARIF output** — `--format sarif`.
- **TY001, TY002** — type/docstring contradiction rules.
- **`[tool.docpact.per-file-tier]`** — per-file tier override (was `tiers`; renamed with deprecation warning).
- **`--add-suppression`** — baselining flag; adds `# nodo: CODE -- reason` to all currently-failing lines.

### Dropped (out of scope for v0.2)

- **HEUR rules** — threshold for "bad" vs. "concise" has no concrete spec. Dropped until real demand surfaces.
- **Sphinx/RST docstring parser** — no demand. Infrastructure ready when needed.
- **Third-party rule plugin API** — premature; internal rules only.
- **Semantic mode** (`SEM` namespace) — LLM-based analysis. No timeline.
- **DOC098** (doctest exception) — **explicitly out of scope, not merely deferred.**
  Executing docstring Examples sections has arbitrary side effects. No safe
  sandboxing strategy exists for a structural linter. The rule stub remains in
  the registry so the code is reserved; the check function is permanently empty.

### Deferred with reasoning

- **pytest plugin** — `docpact[pytest]` extra declared, `docpact.testing`
  programmatic API exists.
  **Why deferred:** In 2026, IDE UX is not the primary value driver for this kind
  of tool. docpact is primarily a CI tool; failures surfaced by `docpact check src/`
  land at the same point in the pipeline as pytest failures. The incremental value
  of a pytest plugin is low unless the target user base explicitly needs IDE
  inline-diagnostics or per-function contract tests. Revisit if adopters request it.

- **DOC051 — Constraints section duplicates Annotated metadata**
  The conceptual distinction is correct: type-expressible constraints (`MaxLen(N)`,
  `Ge(N)`, `Le(N)`, regex patterns, nullability) belong in `Annotated[T, ...]` or
  `Literal[...]`, not re-stated in prose where they can drift out of sync with the
  annotation. The `Constraints:` section is for external-world considerations —
  business rules, SLAs, ADR references, operational limits, deployment risks — that
  the type system cannot encode.

  **Why deferred:** The shipped heuristic (extract numeric values from `MaxLen`,
  `Ge`, etc.; check if that number appears anywhere in the Constraints body) is too
  coarse. Legitimate Constraints entries often cite the same number as the annotation
  but for a different reason: the annotation enforces the technical bound, the
  Constraints entry names the business source ("4096 per API contract — see ADR-012").
  A numeric substring match cannot distinguish these cases, so the rule produces
  false positives on well-written docstrings.

  **To implement correctly:** needs semantic matching — comparing what the annotation
  constraint *means* against what the Constraints prose *says*, not raw numeric
  presence. Candidate approaches: AST-level structured comparison, NLP phrase
  similarity, or requiring a structured Constraints format. None are ready.

  **Code DOC051 is reserved.** The rule will ship under that code when a
  sufficiently precise detector exists.

---

## v0.3 scope

### Shipped ✓ (2026-05-19)

All four priorities delivered. See "Recent changes (post-v0.2)" above for detail.

### Priorities (ordered — all done)

1. **`--changed-only <git-ref>`** — restrict checks to files changed relative to a
   git ref (e.g. `main`, `HEAD~1`). Eliminates the adoption path friction for teams
   who want docpact in CI before they've cleaned up the backlog but don't want to
   use `--add-suppression`. Usage: `docpact check src/ --changed-only main`.
   Implementation: `git diff --name-only <ref>` + filter the collected file list.

2. **`__all__` awareness in tier assignment** — when a module defines `__all__`,
   functions in the list are definitively public (Tier 2 floor) even if their name
   starts with an underscore or they live in a file without a public-path indicator.
   Functions absent from `__all__` in a module that defines it are definitively
   private (Tier 1 ceiling). Currently docpact infers visibility from file path and
   decorators alone; `__all__` is the explicit contract and should win.

3. **Function-level tier pragma** (`# docpact: tier=3`) — override tier for a single
   function without a glob pattern. Needed when one function in a file is at a
   different tier than the rest, and a file-glob override would be too coarse.
   Syntax: inline comment on the `def` line, same placement rules as `# nodo:`.
   Config: `allow_pragma = true` (opt-in; default off to prevent abuse).

4. **DOC021** — "Defaults to X" drift. Fires when an Args entry contains a
   `Defaults to <value>` phrase and the signature's default does not match.
   Example: `count: Number of items. Defaults to 10.` but `def f(count: int = 5)`.
   Severity: WARNING. No auto-fix (intent is ambiguous — the code or the doc could
   be wrong). ty cannot catch this; it checks type consistency, not default-value
   prose consistency.

### MCP-REG cluster — postponed, outline below

The recon team proposed cross-file rules that validate MCP tool registration
consistency: ToolSpec fields ↔ docstring Args, ToolSpec.description ↔ docstring
summary, ToolSpec.schema ↔ Constraints section.

**Why postponed:** These rules require resolving the type of `ToolSpec(...)` across
files — finding where the class is defined, reading its field names, and correlating
them with the docstring of the function being registered. That is cross-file type
resolution, which is a fundamental architectural boundary for docpact. docpact
operates on one file at a time; it never imports code and has no module graph.
Crossing this boundary would require either (a) a full multi-file AST pass with
import resolution (effectively building a partial type checker), or (b) requiring
the user to annotate the relationship explicitly (defeating the purpose).

**What it would be useful for:** The immediate value is retiring bespoke per-project
test files like `tests/test_contract_discipline.py` that enforce these constraints
with hand-written assertions. A declarative rule would be more robust and require
no per-project maintenance. The long-term value is catching silent drift when a
ToolSpec is updated but the tool docstring is not.

**Decision pending:** Whether docpact should ever cross the per-file boundary at all.
If the answer is no, MCP-REG-001 is permanently out of scope. If the answer is yes,
it needs an ADR and a new architectural layer. Not deciding now.

---

## Considered and decided not to implement

These are decisions that surfaced during design or adoption discussions and were
explicitly rejected. Recorded here so the reasoning is not relitigated.

- **DOC020** — type in docstring ≠ type annotation. Fires when an Args entry
  contains an explicit type (e.g. `count (int): ...`) that doesn't match the
  annotation. **Rejected:** Modern Python codebases do not write types in docstring
  Args entries when they have full type annotations — the pattern is dying. For the
  codebases that still do, the discrepancy is caught by ty (for return types) or
  is harmless noise. The signal-to-noise ratio is too low. Code reserved.

- **DOC030** — undocumented exception. Fires when a function raises an exception
  not listed in the Raises section. **Rejected:** Static analysis of `raise`
  statements produces high false-positive rates from transitive exceptions (a
  function that calls `dict[key]` implicitly raises `KeyError`; a function that
  calls any I/O raises `OSError`). Exhaustive Raises sections for most functions
  would be counterproductive. The rule could be narrowed to explicit `raise` at
  the top level, but that case is already caught by careful code review and is
  not worth a lint rule.

- **REF001** — broken `See Also` links. Fires when a `See Also` section references
  a symbol that does not exist in the module. **Rejected:** Out of scope. docpact
  is a docstring structure linter, not a cross-reference resolver or link checker.
  Symbol resolution requires import analysis or a full index of the project.

- **MCP-REG-003** — ExamplePair validation. Specific to one team's internal
  `ExamplePair(input=..., output=...)` structure for illustrating MCP tool
  behavior. **Rejected:** Not generalizable. A team-specific pattern should be
  enforced with a team-specific test or a project-local plugin, not a built-in
  docpact rule.

- **`--baseline` file** — persist suppressed violations to a JSON file (ruff's
  approach with `per-file-ignores`). **Superseded:** `--add-suppression` writes
  inline suppressions, which is more explicit, diff-friendly, and requires no
  out-of-band file to stay in sync. The inline approach also survives file renames.

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
- `DOC050`: registered stub at this phase; implemented post-v0.1 (see "Recent changes").
- `DOC098`: permanently out of scope (see "v0.2 scope").
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

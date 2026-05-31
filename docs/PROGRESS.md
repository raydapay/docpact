# Implementation progress

Tracks phase completion and per-module status. Update this file when a phase
ships; do not put status in CLAUDE.md.

---

## Current status

**v0.1 complete. v0.2 complete. v0.3 complete. Codebase is self-hosting.**

Active rules: DOC001–DOC003, DOC007, DOC012–DOC014, DOC021–DOC022, DOC050, DOC052,
DOC099, MCP001, FIX001–FIX004, TY001–TY002, PARSE001, REG001–REG002, REG010–REG011, SEM001.
DOC051 (Annotated constraint dup) and DOC098 (doctest) reserved/deferred; REG003/REG050/DOC020 reserved.
REG and SEM are opt-in; SEM001 is advisory via `docpact semantic` (ADR-008); REG010/REG011 are
cross-file, run only under `docpact check --crossfile` (ADR-009/010).
(Run `docpact list-rules` for the authoritative current set.)

No active milestone.

---

## Performance baseline (2026-05-30)

Measured on docpact's own `src/docpact` corpus. **Wall-time rots as the codebase
grows — compare throughput (fn/s, lines/s), not raw milliseconds, and re-stamp the
corpus size when re-measuring.** Machine: WSL2 Linux, 16 cores (fork-based).

Corpus at measurement: **51 files, 6,800 physical lines, 164 functions.**

| Run | Wall-time | Throughput |
|---|--:|--:|
| serial (`jobs=1`) | 247–253 ms | ~648 fn/s · ~27k lines/s |
| parallel (`jobs=16`) | ~102 ms | ~1.6k fn/s (2.5×) |

Where serial time goes (median of 15 runs, temporary instrumentation, not committed):

| Stage | Share |
|---|--:|
| rules + dispatch + everything else | **68%** |
| `extract_functions` (AST + FunctionInfo + byte-offset table) | 22% |
| `parse_suppressions` (tokenize scan) | 8% |
| docstring parse (griffe `Docstring` + `parse_google`) | **3%** |

**Key finding — griffe docstring parsing is ~3% of runtime, NOT a hot path.** An
earlier working assumption that griffe was "the heaviest per-function cost" was
wrong; this measurement refutes it. Any griffe-removal or Rust-extension decision
must therefore be justified on grounds *other than* docstring-parsing speed. The
real hot paths are the rule loop (68%) and AST/FunctionInfo extraction (22%) — both
already addressed by process parallelism (the 2.5× above), neither touched by
docstring parsing. The cleanly-FFI-extractable component (the docstring state
machine) is not the slow component; they do not coincide.

**Decision (ADR-006 item 6, 2026-05-30):** keep griffe; do not reimplement docstring
parsing (Python or Rust). At 3% of runtime the work has no perf basis and the
dependency-hygiene benefit does not outweigh ~200 LOC + regression risk. Revisit
only on a forced griffe 2.0 migration, griffe going unmaintained, or a profiler
showing docstring parsing has become material. See ADR-006 for full why/why-not.

---

## Cross-file analysis via LSP (`docpact[crossfile]`) — ADR-009 + ADR-010 — SHIPPED

**Shipped (all 5 steps; ADR-009 + ADR-010).** Opt-in, provider-agnostic, LSP-backed
cross-file resolution → FR-1 (Args block ↔ imported Pydantic model fields parity, REG010)
and FR-2(b) (imported-handler Tier-3 floor + signature parity, REG011) + the cross-file ×
semantic composition. Deterministic, static (server resolves without executing),
server-swappable. The default per-file `check` stays offline and unchanged. The step plan
below is retained as the build record; see the per-step "SHIPPED" notes.

**Reuse (don't reinvent):** `scripts/spike_lsp.py` is working LSP-client code (framing,
JSON-RPC, handshake, `textDocument/definition`, re-export resolution — all proven) →
graduate it. `src/docpact/semantic/backend.py` is the provider-agnostic-protocol +
factory pattern to mirror. `doc050_pydantic_field.py` has the Pydantic field-walk to
reuse. The docstring parser parses the `Args:` block. REG already extracts registry
entries.

**Cross-cutting invariants (do not violate):**
- **No real LSP server in CI.** All tests mock the server (a fake stdio JSON-RPC peer).
  ty/any server is a *runtime* opt-in dep, never a `make verify` dependency — `check`
  stays offline and deterministic.
- **Strictly opt-in.** Cross-file runs only when enabled AND a server is available;
  the default `check` is untouched. Graceful degradation (server missing/old → clear
  error or skip, never crash).
- **Run `make verify` before the final commit** (it writes — stats/docs), per the
  Definition of done.

### Step 1 — LSP client layer (graduate the spike) — SHIPPED
- **Build:** `src/docpact/lsp/client.py` — provider-agnostic `LSPClient` (context
  manager): spawn the configured server, `initialize`/`initialized`, `didOpen`,
  `definition(file, line, char) -> list[Location]` normalizing `Location` |
  `LocationLink`, clean `shutdown`/`exit`; raise `LSPError` on missing server / timeout
  / bad response. `[tool.docpact.lsp]` config (`server` cmd, default `["ty","server"]`;
  `timeout`) → `LspConfig` in `config.py`.
- **Exit:** resolves a definition against a *fake* in-process server in tests; missing
  server → `LSPError`; `make verify` green (new code dogfood-clean + covered); zero
  real-server use in CI.

### Step 2 — REG extraction extension (capture model ref + description Args) — SHIPPED
- **Build:** extend tool-registry extraction to also capture, per entry, the
  `input_model` symbol *reference + source position* (for LSP) and the description
  string's `Args:` keys (via the docstring parser). Backward-compatible; literals/Name
  only (skip dynamic).
- **Exit:** entries carry the new fields when present; all existing REG tests pass
  unchanged; new extraction unit tests.

### Step 3 — FR-1 cross-file parity rule — SHIPPED
- **Build:** an opt-in cross-file pass: for an entry whose `input_model` is imported,
  `LSPClient.definition` → defining file → AST-extract the model's fields (reuse DOC050)
  → compare bidirectionally to the entry's `Args:` keys → emit findings. Deterministic.
- **Decisions to make here (flag):** (a) **code/namespace** — REG-continuation (e.g.
  REG010) vs a new `XF` namespace; (b) **invocation** — `docpact check --crossfile`
  flag vs a separate subcommand. Recommend: new code in REG family + `--crossfile` opt-in
  on `check` (deterministic → belongs with check, gated by flag + server availability).
- **Exit:** parity fires on a two-file fixture (match / missing-in-doc / missing-in-model)
  driven by a *fake* LSP server; opt-in; `make verify` green.

### Step 4 — packaging + docs — SHIPPED
- **Build:** `docpact[crossfile]` extra (optional server dep); README + ADOPTING
  cross-file section (`[tool.docpact.lsp]`, server-swappable note, opt-in/perf caveats);
  spec status + new rule in §15.3; `make docs` for the new rule doc.
- **Exit:** docs current; `list-rules` shows the new code; `make verify` green.

### Step 5 — FR-2(b) handler correlation + cross-file Tier-3 floor (ADR-010)

Scoped and accepted as ADR-010. The Tier-3 floor for an *imported* handler is
reverse-direction (the registration fact lives in another module), so `--crossfile`
runs a **pre-pass** that resolves all handler/model references in one LSP session
and produces the floor *before* per-file tier assignment. The floor raises the tier
and the existing rule engine enforces Tier 3 (bounded amendment to ADR-003:
project-level- not file-level-deterministic, under `--crossfile` only). Same
resolution also feeds the semantic layer (ADR-010 "one resolution, two consumers").

- **Increment 1 — SHIPPED:** handler-ref + `description_text` extraction
  (`handler_field` config); `--crossfile` pre-pass + imported-handler Tier-3 floor;
  `semantic --crossfile` (floor → scope, resolved model fields + registry
  description → prompt context).
- **Increment 2 — SHIPPED:** REG011 (imported-handler *signature* ↔ schema/model
  parity), the cross-file analogue of REG001. Phantom-direction only; skips the
  model-instance and `**kwargs` handler shapes to stay low-false-positive. Runs in
  the same `--crossfile` pre-pass; resolver resolves per-rule severities from config.

**Performance — measure, don't guess (ADR-009 RT-2).** The cross-file pre-pass is
serial (one LSP session); the per-file analysis still parallelizes under `--jobs`.
`docpact bench --crossfile` reports the pre-pass cost broken into server spawn+init
vs. query time (+ slowest query, which usually carries the server's first workspace
index), so an adopter can see on *their own tree* what dominates. Two optimizations
are **data-gated on that breakdown, not yet built**: (1) a persistent/warm server to
amortize spawn+index across runs (wins when startup/index dominates); (2) concurrent
(pipelined) `definition` requests within the *one* session (wins when query
round-trips dominate). Spinning one LSP session *per worker* was considered and
rejected: each session re-indexes the whole workspace, so it N×'s the dominant cost
(indexing) and the memory — the opposite of help on a heavy codebase.

**Validated against real `ty server` (0.0.37), 2026-05-31** — not just the offline
fake. `docpact check --crossfile` with `server = ["ty", "server"]` resolved and
fired correctly on: a direct cross-module import (REG010 + REG011), a re-export
chain (`pkg/__init__` re-exports `pkg.schemas.X`; REG010 resolved through it), and
an aligned workspace (no false positives). `check src/ --crossfile` on docpact's own
tree exits 0 (no registries → no findings, no crash). The CI gate still uses only the
fake server (offline/deterministic); real-server use stays opt-in.

**Sequencing:** each step is independently shippable and non-breaking — Step 1 ships
unused, Step 2 is backward-compatible, Step 3 is the opt-in rule, Step 4 is docs,
Step 5 increment 1 is the floor + semantic composition.
`scripts/spike_lsp.py` and `scripts/spike_semantic.py` were deleted once their
features shipped.

---

## Recent changes (post-v0.3)

### SEM001 prompt hardening — adopter issue #11 (2026-05-31)

First real-codebase adopter run (an MCP server, `gpt-4o-mini` via GitHub Models)
reported deterministic SEM001 false positives: substantive `Returns:` sections
flagged as "restates the type" (the model judged the opening phrase, not the
body), and `Raises: None.` flagged for "not clarifying" — a contradiction with
DOC013, which *requires* the canonical `None.`. The `SYSTEM` prompt was hardened:
read each section in full; canonical-empty (`None.`, "Does not return a value")
is correct and never flagged; a Returns naming a side effect / what is
written/sent / status codes / units is signal; and a weak/empty verdict MUST
quote the offending span (text that names an effect/meaning can never be that
span). Validated against real `gpt-4o-mini` — all three FPs cleared across 3
stable runs, genuine cargo-cult still caught with cited evidence; `gpt-4o` was
clean even before the loophole clause. Prompt-intent regression guard added
(real-model behaviour can't be unit-tested — the §19 reliability gap). README
notes SEM quality scales with model; advisory framing held up exactly as designed.

### Semantic layer (SEM) opened — 2026-05-30

ADR-008. A spike (`scripts/spike_semantic.py`, GitHub Models; since removed once
the feature shipped) validated the LLM
signal: 26/26 well-documented real agent tools verdict "good" (no false positives);
planted cargo-cult/hidden-contract caught. So the long-deferred semantic mode is now
active, scoped to what the spike proved.

- **`SEM001`** — weak/empty docstring (cargo-cult, hidden contract, empty Returns).
  The DOC051/REG050 *intent* delivered in the advisory layer; DOC051/REG050 stay
  reserved/deterministic (not revived).
- **`docpact semantic`** command — opt-in, advisory, **separate from `check`** (never
  in `make verify`/dogfood, so `check` stays deterministic and offline). `--dry-run`
  prints prompts and sends nothing; `--min-tier` scopes (default 3); `--exit-zero`.
- **Pluggable backend** (`docpact.semantic.backend`): `LLMBackend.complete(system,
  user) -> str` protocol + factory. One adapter ships — `OpenAICompatBackend` (GitHub
  Models, OpenAI, OpenRouter, Azure, local Ollama/vLLM). Gemini/Anthropic-native = one
  new adapter class, no analyzer/CLI change. Stdlib `urllib` only (no new dep).
- **`[tool.docpact.semantic]`** config: backend, model, api_base, api_key_env, min_tier.
- Analyzer reuses `FunctionInfo` + the diagnostic model + output formatters; findings
  are `RuleResult` (code SEM001) so text/JSON output and `list-rules` work unchanged.
- 22 tests (config, backend via mocked urlopen, analyzer via FakeBackend, CLI incl.
  dry-run); no network in tests. GitHub Models = free on-ramp; BYOK to scale.

### tokenize-based suppression scanner — 2026-05-19

`parse_suppressions` replaced the line-by-line text scan with
`tokenize.generate_tokens`. The tokenize module emits `COMMENT` tokens only
for actual Python comments — triple-quoted docstrings, inline strings, and
f-strings are invisible to the scanner.

Root cause of false FIX003 warnings: 7 source files contain suppression syntax
examples in their module docstrings (suppress.py, baseline.py, fix001/002/003,
doc003, doc022). The old scanner created phantom suppression records for those
lines; FIX003 then fired because no real violation existed on them. The 7-entry
`per-file-ignores` workaround in `pyproject.toml` is removed.

`tokenize.TokenError` on broken source returns partial results rather than
raising; PARSE001 owns parse failures at the file level.

7 new tests in `test_suppress.py`. `suppress.py` is now at 100% coverage.

### PARSE001 — Python syntax error rule — 2026-05-19

Replaces the unhandled `SyntaxError` traceback from `extract_functions` with
a structured diagnostic.

- New `PARSE` namespace: `src/docpact/rules/parse/`. `PARSE001` fires at
  ERROR severity when a file cannot be parsed; all other checks for that file
  are skipped — structural analysis requires a valid AST.
- `_run_checks` wraps `extract_functions` in try/except; on SyntaxError emits
  PARSE001, adds results to the accumulator, and `continue`s to the next file,
  skipping the function-level loop and FIX003 post-pass.
- Position extracted from `SyntaxError.lineno` / `offset` (1-based offset
  converted to 0-based column; None guards in place).
- `PARSE` added to default `select` in `config.py` and to docpact's own
  `pyproject.toml` self-check.
- Flows through all output formatters (text, JSON, SARIF, GitHub).
  Inline `# nodo: PARSE001` suppression works via the existing text-based
  `parse_suppressions` (handles invalid Python fine).
- 16 tests: unit (position extraction, None guards, severity override, stub
  returns `[]`) + CLI (text/JSON/SARIF, `--select PARSE`, `severity=off`,
  inline suppression).

### External dry-run response — 2026-05-19

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

**Shipped (was inbox #2, #3):**
- `--config` flag for explicit pyproject.toml path (`load_config_from`).
- `per-file-tier` glob anchoring to project root (`file_tier_override_for`).
Both shipped in a later UX pass; inbox is empty.

### DOC022 — typed prose annotation mismatch — 2026-05-19

Fires when an Args entry contains an explicit inline type (`name(type): desc` form)
that doesn't match the parameter's signature annotation. Entries without an inline
type are ignored entirely — same "only check what you asserted" principle as DOC021.

Comparison is plain string equality after whitespace strip. No semantic
normalization. Known false positives from notation differences (`Optional[str]` vs
`str | None`, `List[int]` vs `list[int]`) are documented in the module docstring
and pinned by tests. Primary target: post-refactoring drift where the signature
changes from `int` to `float` but the prose isn't updated.

`SectionEntry` gains `type_annotation: str | None = None` (backward-compatible
default). Parser now propagates `p.annotation` from griffe through both Google
and NumPy paths.

### External dry-run follow-up (round 2) — 2026-05-19

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
- **Semantic mode** (`SEM` namespace) — ~~LLM-based analysis. No timeline.~~
  **Opened 2026-05-30 (ADR-008)** after a spike validated the LLM signal. SEM001
  (weak/empty docstring) ships via `docpact semantic`, advisory, with a pluggable
  LLM backend. See the "Semantic layer opened" entry above.
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

### MCP-REG cluster — partially resolved by ADR-005 (2026-05-30)

**Update:** The *same-file* case is now decided — see ADR-005 (Accepted). The
postponement below conflated two axes: schema *dialect* (cheap) and *locality*
(the only hard axis). Same-file tool registries need no cross-file resolution and
are in scope (new `REG` namespace: REG001 phantom-param, REG002 unmatched-entry,
plus a Tier 3 floor from registry membership). Cross-file registration — the
imported-function pattern below — remains out of scope and still needs the
module-graph decision. The original outline is kept for that cross-file case:

An adopter team proposed cross-file rules that validate MCP tool registration
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

**Decision (ADR-006, 2026-05-30):** docpact stays per-file for the interim. A
hand-rolled module graph is vetoed (false-positive tar pit); the strategic path for
cross-file is to consume an existing resolver once a stable interface exists.

**Update (ADR-009, 2026-05-30):** that interface turned out to be **LSP** — ty (and
any type checker) speaks it, and a spike proved `textDocument/definition` resolves the
imported-model pattern incl. re-export chains, statically. **Cross-file is now opened**
as an opt-in, provider-agnostic **LSP-client** capability (FR-1 Args↔imported-model
parity, FR-2(b) handler correlation) — deterministic, server-swappable (ty/pyright/…),
no bespoke ty API. The hand-rolled-graph veto stands; the per-file `check` default is
unchanged. **Decision made; build pending.** See ADR-009.

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

- **LSP server as a griffe replacement** — after adopting an LSP client for
  cross-file (ADR-009), reuse the server to parse docstrings and drop griffe.
  **Rejected — different layer, zero overlap.** griffe parses the *internal
  structure of a docstring string* into Google/NumPy sections (`Args` keys,
  `Returns`/`Raises` bodies); LSP resolves *symbols across files* and has no
  concept of a docstring's section structure. The raw docstring text already
  comes from stdlib `ast`, not griffe, so LSP would contribute nothing to the
  parse — we'd still need a section parser. Worse, routing the per-function path
  through a server would break the default `check`'s offline/zero-dep/fast/
  deterministic guarantees (a server for every function, every run; non-
  deterministic hover rendering). The keep-griffe decision stands on its own
  (ADR-006 item 6: ~3% of runtime, no perf basis to reimplement); LSP is not a
  candidate replacement and is far heavier for this task.

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

# CLAUDE.md

This file is auto-loaded by Claude Code on every session in this repository. It establishes context, conventions, and constraints for implementation work. Read it before doing anything else.

The same content applies to other agents (`AGENTS.md`, `GEMINI.md`). Copy this file to those names if needed; treat them as equivalent.

---

## Project context

`docpact` is a docstring contract validator for Python. It validates that function docstrings are structurally consistent with their signatures, that required information is present for the function's audience, and that conflicts between metadata sources (decorator vs. docstring) are surfaced rather than silently inconsistent.

The project is targeted at three machine audiences: MCP clients consuming generated schemas, coding agents reasoning about whether modifications are safe, and CI pipelines enforcing contracts at merge time. Human developers are a secondary audience.

**Current status: Phase 1 complete.** The specification and foundational ADRs are accepted. `parser/source.py` (AST-based `FunctionInfo` extraction) and `parser/docstring.py` (`GoogleParser`) are implemented and fully tested (85 tests, all passing). Phase 2 (tier assignment + rule registry) is next.

**The project owner is Ray.** Address him directly when asking questions. Ray's working preferences are documented below under "Working with Ray."

---

## Read first, in this order

1. **`docs/spec/docpact-spec.md`** — the specification. Source of truth for what docpact is. Read it fully before writing any code. ~1200 lines.
2. **`docs/adr/README.md`** — ADR index and process.
3. **`docs/adr/ADR-001-implementation-language.md`** — why Python + griffe, and what alternatives were rejected. Critical for understanding constraints.
4. **`docs/adr/ADR-002-docstring-format-baseline.md`** — why only Google style in v0.1.
5. **`docs/adr/ADR-003-tier-assignment.md`** — why tier is derived from context, not declared per-function.
6. **`PROJECT_STRUCTURE.md`** — directory layout and design rules for the codebase.
7. **`pyproject.toml`** — dependencies, tooling configuration, scope of dev environment.

After reading, examine the existing skeleton under `src/docpact/`. Every module has a docstring explaining its purpose. Functions have stubs that raise `NotImplementedError` — those are your implementation targets.

Do not start writing code until you have read the specification end-to-end. The spec contains constraints and definitions that are not obvious from the file structure alone.

---

## Mission

Implement docpact v0.1 per the specification. v0.1 scope is bounded and defined in spec §5.1:

- Structural mode only (deterministic checks)
- Google docstring parser
- Tiers 1, 2, 3 (Tier 4 partial — explicit configuration only)
- Rule namespaces: `DOC`, `MCP`, `FIX`, `HEUR` (HEUR namespace allocated, no rules in v0.1)
- Commands: `check` (with `--fix` and `--unsafe-fixes`), `generate`, `show-schema`, `list-rules`
- Configuration via `pyproject.toml` and `docpact.toml`
- Pre-commit integration
- Output formats: text, JSON

The DOC rules to ship in v0.1 are documented inline in the spec. At minimum:

- `DOC001` — missing docstring
- `DOC007` — Args/signature parameter mismatch
- `DOC012` — required section missing for tier
- `DOC013` — empty section in non-canonical form
- `DOC014` — suspicious parameter name mismatch (no fix)
- `DOC050` — Pydantic field missing description
- `DOC051` — constraint duplicates `Annotated` metadata
- `DOC098` — example raised an exception
- `DOC099` — `[FILL]` stub marker not replaced

MCP rules to ship:

- `MCP001` — decorator description and docstring MCP section both present

`MCP002` is **not in v0.1**. The structural case (neither `MCP:` section nor
decorator `description=` present on a Tier 3 function) is covered by `DOC012`.
The quality/completeness variant ("description is insufficient") requires
semantic understanding and belongs in the `SEM` namespace when semantic mode
ships.

FIX rules to ship:

- `FIX001` — bare `# noqa` without a documented reason

This list is not exhaustive — refer to the spec for the complete set and add others as needed to fulfill spec requirements.

---

## Out of scope for v0.1

Per spec §5.3 and §5.4, the following are **explicitly excluded** from v0.1:

- **Semantic mode** (`SEM` rule namespace). The entire LLM-based analysis subsystem. No semantic analyzer, no prompts, no API client integration. The `SEM` namespace prefix is allocated in the rule code convention but no rules of that prefix exist in v0.1.
- **NumPy and Sphinx docstring parsers.** Only Google style ships in v0.1. The parser abstraction must remain in place so these can be added in v0.2+ without changing the rule engine.
- **`pytest` plugin.** The `pytest` extra in `pyproject.toml` is declared but the plugin code itself is v0.2 work. The `docpact.testing` programmatic API ships in v0.1 instead.
- **SARIF output.** v0.2 target. Only text and JSON in v0.1.
- **`TY` rules** (ty cross-validation). v0.2 target.
- **Heuristic rules** (`HEUR` namespace). Namespace allocated, no rules.
- **Third-party rule plugin API.** Rules are internal to docpact in v0.1.
- **Tier 4 automatic detection.** Tier 4 requires explicit configuration in v0.1.
- **`format` subcommand.** Folded into `check --fix` in v0.1.

If you find yourself implementing any of the above, stop. Either you have misread the spec or you have drifted into v0.2 work. Confirm with Ray before continuing.

---

## Architecture quick reference

The full architecture is in spec §7. Summary:

```
CLI (cli.py)
  ↓
Rule engine (tier assignment → rule selection → diagnostic emit)
  ↓
Structural analyzer (rules/) operating on:
  ├── FunctionInfo (model/function_info.py)
  └── ParsedDocstring (model/parsed_docstring.py)
  ↓
DocstringParser abstraction (parser/docstring.py)
  ├── GoogleParser (v0.1)
  └── (NumPy, Sphinx in later versions)
  ↓
Python AST (stdlib `ast`) + griffe
```

Key invariants:

- **Rules are pure functions.** They receive `(FunctionInfo, ParsedDocstring | None, RuleConfig)` and return `list[RuleResult]`. They do not modify files, do not access global state, do not perform I/O.
- **The model layer has no behavior.** `model/*.py` contains frozen dataclasses only. Methods beyond dataclass essentials do not belong there.
- **The parser is the only place that touches griffe and `ast`.** All downstream code operates on model types.
- **Tier assignment is deterministic.** Same input, same output. See ADR-003 and spec §10.1.
- **Error codes are stable API.** Once a code is shipped, it never changes meaning or gets reused. See spec §18.1.

---

## Conventions

### Dogfooding

docpact's own code should pass its own checks. Once enough of the tool exists to run on itself, add it to the pre-commit hook for this repo. Stub docstrings already in the skeleton mostly conform; new code must also conform.

### One rule per file

Rules live in `src/docpact/rules/<namespace>/<code_lowercase>_<descriptive_slug>.py`. Each file exports one rule via the `@register(RuleMetadata(...))` decorator. No central rule catalog to keep in sync.

### Tests alongside implementation, not after

When you implement `rules/doc/doc007_param_mismatch.py`, you also create `tests/test_rules/test_doc007.py` in the same change. Tests are not a separate phase. A change is incomplete without them.

### Tests are additive

Don't modify existing passing tests unless their contract genuinely changes. Add new test classes or functions for new coverage. A future agent session has no memory of prior work — the test suite is the persistent record of what invariants must hold. If a future session could miss an invariant without the test, the test stays.

### Fixtures are real Python files

Test fixtures live in `tests/fixtures/` as actual `.py` files demonstrating specific cases. Each fixture is minimal and self-contained. Do not embed Python source as triple-quoted strings in test files except for one-off cases that are not worth a fixture.

### Reproducibility

Configuration is deterministic. Tier assignment is deterministic. Rule output is deterministic. If a result depends on file ordering, environment variables, or wall-clock time, that is a bug.

### No imports of analyzed code

docpact must never `import` the code it is analyzing. All analysis is static. This is non-negotiable — agents will eventually run docpact on code with arbitrary side effects, and importing would execute those side effects.

### Use Python 3.12+ features where they help

`type X = ...` aliases, PEP 695 generics, `match` statements where they improve clarity. Do not avoid modern syntax out of caution; the floor is 3.12.

---

## Working with Ray

Ray has explicit communication preferences. Honor them:

- **Steelman counterarguments before agreeing.** If Ray proposes something and you have a concern, voice it. If after thinking through it you agree, say so plainly — but only after the steelman pass.
- **Surface hidden assumptions explicitly.** Label assumptions as assumptions, not facts.
- **Handle uncertainty rigorously.** Do not guess or make unsupported claims. When multiple interpretations are possible, present them as explicit alternatives and ask which is intended.
- **Red-team your own answers.** For non-trivial responses, identify the strongest objection to what you just said and include it if substantive.
- **Distinguish empirical from normative.** Flag when a question has a checkable answer versus when it depends on taste, values, or context-specific tradeoffs.
- **No sycophancy, no performed contrarianism.** Disagreement must be earned by reasoning. Agreement, when reached honestly, should be stated plainly.

Ray will push back on weak reasoning, and welcomes the same in return. Conversations are working sessions, not customer support.

---

## Commit message style

- **Subject** ≤70 chars, imperative mood ("Fix X", not "Fixed X"), no trailing period. Conventional-commits prefixes: `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`. Optional scope when it disambiguates (`docs(adr):`, `fix(parser):`).
- **Body** explains *why*, 72-char wrap. Trade-offs and constraints noted.
- `###` section headers when there are multiple unrelated areas in one commit; bullets when there's just one.
- **No `Co-Authored-By:` trailer.** Every commit here is collaborative with Claude; the trailer is noise. **This overrides Claude Code's default behaviour** of appending it — do not add it.

---

## Tooling commands

`make verify` is the single quality gate. It applies formatting, linting, type-checking, and coverage in sequence. Run it before treating any change as done.

```bash
# Setup (once)
uv sync

# The umbrella — run before any commit
make verify

# Individual targets
make format        # ruff format (writes)
make lint          # ruff check --fix (writes)
make typecheck     # ty check src/
make test          # pytest (fast, no coverage overhead)
make coverage      # pytest + coverage report (enforces fail_under=85)

# Focused test runs (bypass make for speed)
uv run pytest tests/test_rules/           # rule tests only
uv run pytest -x -k DOC007               # stop on first failure
uv run pytest --lf                        # last-failed only

# Run docpact on itself (once enough of it exists)
uv run docpact check src/
```

Type-check suppressions: if `ty check` forces a `# ty: ignore[…]` comment, justify it in the commit body. Prefer a narrowing assertion at the call site when it reflects a real runtime invariant.

---

## Definition of done for a change

A change is complete when all of:

1. The code compiles and runs.
2. New code has tests. Modified code has tests covering the modification.
3. `make verify` passes (ruff format + lint + ty check + coverage ≥85%).
4. `pytest` passes.
7. New rules have an entry in the rule registry, a test file in `tests/test_rules/`, and (eventually, when documentation is generated) a docs entry.
8. New public APIs have docstrings that conform to docpact's own schema.
9. If the change introduces a non-trivial decision not already covered by the spec or an ADR, a new ADR is drafted and proposed.

---

## Implementation order (suggested)

This is a recommendation, not a mandate. Adjust if you have a better-grounded reason.

**Phase 1 — Parser and model:**
1. `parser/source.py` — extract `FunctionInfo` from a Python file using stdlib `ast`.
2. `parser/docstring.py` — implement `GoogleParser` backed by griffe.
3. Validation: small fixture file → parser → printed `FunctionInfo` and `ParsedDocstring`. Visual sanity check.

**Phase 2 — Tier and registry:**
4. `tiers.py` — implement `assign_tier` per spec §10.1.
5. Tests for tier assignment covering every rule in §10.1.
6. Verify `rules/_registry.py` works end-to-end with at least one stub rule that registers cleanly.

**Phase 3 — First rules:**
7. `DOC001` (missing docstring) with safe fix that inserts a stub.
8. `DOC007` (param mismatch) with safe fix.
9. End-to-end CLI: `docpact check fixture.py` produces correct text output.

**Phase 4 — Configuration:**
10. `config.py` — pyproject.toml / docpact.toml loading with all spec §14 keys.
11. Wire config into rule selection and tier overrides.

**Phase 5 — Fix engine:**
12. Apply fixes in-place. Conflict detection (no overlapping ranges).
13. `--fix` and `--unsafe-fixes` flags.
14. `--diff` flag for dry-run.

**Phase 6 — Output:**
15. JSON output format with stable schema.
16. Suppression handling (`# noqa: CODE`).

**Phase 7 — Remaining rules:**
17. `DOC012`, `DOC013`, `DOC014`, `DOC050`, `DOC051`, `DOC098`, `DOC099`.
18. `MCP001`, `MCP002`.
19. `FIX001`.

**Phase 8 — Supporting commands:**
20. `generate` (stub emission).
21. `show-schema` (tier requirements display).
22. `list-rules`.

**Phase 9 — Testing API:**
23. `docpact.testing` public functions.

**Phase 10 — Polish:**
24. Pre-commit hook configuration in repo.
25. Documentation page generation per rule code.
26. Self-application (dogfooding) on docpact's own source.

After Phase 3 the tool is minimally useful (catches the highest-value violations). After Phase 7 v0.1 is feature-complete. Phases 8-10 finish the release.

---

## ADR process

ADRs are how this project records significant design decisions. The process is documented in `docs/adr/README.md`. Summary:

- A decision warrants an ADR if it is hard to reverse, has cross-cutting consequences, or competent engineers might reasonably disagree on the answer.
- ADRs are numbered sequentially. Numbers are never reused.
- Use `docs/adr/template.md` as the starting point.
- Status moves through `Proposed → Accepted → (eventually) Superseded by ADR-NNN`.
- Once accepted, ADRs are not edited in place. Material changes require a new ADR.

When in doubt about whether to write an ADR, ask Ray.

---

## What to stop and ask before doing

Some decisions belong to Ray, not to you. Stop and ask before:

- **Modifying the specification.** The spec is the contract. Implementation decisions follow it; they do not change it. If the spec is ambiguous or wrong, raise that explicitly rather than picking an interpretation silently.
- **Adding a new dependency to `pyproject.toml`.** Every dependency is a long-term commitment. Justify before adding.
- **Introducing a new architectural pattern.** The architecture is described in spec §7 and the ADRs. Departures need their own ADR and Ray's sign-off.
- **Reordering or renaming error codes.** Codes are stable API. Once shipped, never reused. See spec §18.1 and ADR-004 (planned).
- **Adding features beyond v0.1 scope** (see "Out of scope" above).
- **Changing tier assignment rules.** Tier rules are deterministic by design. See ADR-003.
- **Changing the file structure.** Layout is documented in `PROJECT_STRUCTURE.md`. Deviation needs justification.

Don't ask permission for routine implementation work — write code, write tests, run the lint/test combo, propose changes. Stop only at the boundaries above.

---

## Common operations

### Adding a new rule

1. Create `src/docpact/rules/<namespace>/<code>_<slug>.py`.
2. Implement the rule function with `@register(RuleMetadata(...))`.
3. Add a test file `tests/test_rules/test_<code>.py` covering positive cases, negative cases, fix behavior (if fixable), and suppression behavior.
4. Add fixtures to `tests/fixtures/` if needed.
5. Update `tests/test_rules/test_registry.py` to verify the rule registers cleanly (likely already automatic once the registry is implemented).
6. Update the rules listing in the docs (if generated) or in the spec's example output.
7. Run the full check.

### Adding a test fixture

Fixtures live in `tests/fixtures/`. Organize by what they demonstrate: `tier3_missing_constraints.py`, `mcp_decorator_docstring_conflict.py`, etc. Each fixture is a minimal, self-contained Python file.

Fixtures are excluded from ruff and from docpact's self-application (see `pyproject.toml` per-file-ignores).

### Updating the spec (rare)

If the spec needs to change, do not edit `docs/spec/docpact-spec.md` directly. Open the question with Ray. Spec changes are deliberate, not incremental. Bump the spec version in the header when changes are accepted.

---

## When stuck

If you genuinely cannot proceed:

1. Re-read the relevant spec section.
2. Re-read the relevant ADR.
3. Check whether the question is empirical (look it up, test it, measure it) or normative (requires a decision).
4. If normative, ask Ray with the alternatives stated as explicit options.
5. If empirical, find the answer and proceed.

Do not silently pick an interpretation and hope it is right. Surfacing ambiguity is part of the work.

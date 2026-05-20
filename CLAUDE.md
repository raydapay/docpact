# CLAUDE.md

This file is auto-loaded by Claude Code on every session in this repository.
It is the agent contract — stable across milestones, task-oriented, short.

The same content applies to other agents (`AGENTS.md`, `GEMINI.md`).
Copy this file to those names if needed; treat them as equivalent.

---

## Current state

**v0.1 complete. v0.2 complete. v0.3 complete. Codebase is self-hosting.**

Active rules: DOC001–DOC003, DOC007, DOC012–DOC014, DOC021–DOC022, DOC050,
DOC098–DOC099, MCP001, FIX001–FIX003, TY001–TY002, PARSE001.
DOC051 (Annotated constraint duplication) is deferred — conceptually sound,
heuristic too coarse. See PROGRESS.md "Deferred with reasoning".

No active milestone. See PROGRESS.md for v0.3 scope and what shipped.

Key facts a fresh session needs:
- Suppression syntax is `# nodo: CODE -- reason` (not `# noqa`). See ADR-004.
  FIX001 fires on bare `# nodo`, FIX002 fires when codes present but no `-- reason`.
- `suppress_comment = ["nodo"]` in `[tool.docpact]` — configurable, accepts a list.
- Suppression must be on the `def` line: `def foo(  # nodo: CODE` — **not** on the
  closing `) -> None:` line. ruff's formatter moves comments there when it wraps
  signatures; that placement silently fails to suppress because docpact matches on
  `func.line` (the `def` keyword line).
- `make verify` is the single quality gate. Run it before treating any change done.
- Generated rule docs live in `docs/rules/`. `make verify` enforces they stay in sync
  with the registry via `docs-check` (`make docs` + `git status --short docs/rules/`).
- File-level rules (DOC002, DOC003, DOC050, FIX001, FIX002) are wired directly in
  `_run_checks` in `cli.py` and skipped in the function-level loop via a code skip set.
- `format = "numpy"` in `[tool.docpact]` selects `NumpyParser`; default is Google.
- docpact's own config uses `select = ["DOC", "MCP", "FIX", "TY", "PARSE"]`.
- `[tool.docpact.per-file-tier]` overrides tier per glob pattern (e.g. `"src/mcp/*.py" = 3`).
  Old key `[tool.docpact.tiers]` still works with a deprecation warning.
  Patterns are anchored to the project root (directory containing `pyproject.toml`). `load_config`
  returns `ConfigResult(config, root)`; matching functions receive `root` and relativize paths
  before fnmatch. `assign_tier` accepts an optional `root` kwarg for the same purpose.
- `--add-suppression` adds `# nodo: CODE -- baseline` to every currently-failing line.
  `--add-suppression --diff` previews without writing. `--suppression-reason TEXT` customises the reason.
- `--changed-only <ref>` restricts checks to `.py` files changed relative to a git ref.
  Exits with a clear error if not in a git repo or ref is invalid.
- `--config PATH` loads configuration from an explicit `pyproject.toml` or `docpact.toml`,
  bypassing the CWD upward discovery walk. Root = `PATH.parent`.
- When a module defines `__all__` as a literal, tier assignment uses it as the
  definitive visibility contract: listed → Tier 2 floor; absent → Tier 1 ceiling.
- `allow_pragma = true` in `[tool.docpact]` enables `# docpact: tier=N` inline on
  `def` lines to override the assigned tier for that function only. Off by default.

**The project owner is Ray.** Address him directly when asking questions. Ray's
working preferences are documented below under "Working with Ray."

---

## Before you start

**Always read first (< 5 min total):**
1. `docs/PROGRESS.md` — current milestone, recent post-v0.1 changes, v0.2 scope.
2. `pyproject.toml` — dependencies, tooling config, docpact self-config.

**Read additionally based on task type:**

| Task | Also read |
|---|---|
| Adding or modifying a rule | Relevant spec section + existing rule file + its test file |
| New config key or CLI option | spec §14–§16 |
| Parser change | spec §8–§9 + ADR-001 |
| Tier assignment change | spec §10.1 + ADR-003 — **stop and ask Ray first** |
| Architecture change or new subsystem | Full spec + all ADRs — stop and ask Ray first |
| Anything else | Start from the code; `PROJECT_STRUCTURE.md` for layout |

Reading the full 1300-line spec before routine work is expensive and unnecessary.
Reserve it for structural decisions.

---

## Architecture quick reference

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

- **Rules are pure functions.** `(FunctionInfo, ParsedDocstring | None, RuleConfig) → list[RuleResult]`. No I/O, no global state, no file mutation.
- **The model layer has no behavior.** `model/*.py` is frozen dataclasses only.
- **The parser is the only place that touches griffe and `ast`.** All downstream code operates on model types.
- **Tier assignment is deterministic.** Same input, same output. See ADR-003 and spec §10.1.
- **Error codes are stable API.** Once a code is shipped, it never changes meaning and is never reused. See spec §18.1.

---

## Conventions

### Dogfooding

docpact's own source passes its own checks on every CI run (`docpact check src/`).
All new code must conform. Suppressions require a `-- reason`.

### One rule per file

Rules live in `src/docpact/rules/<namespace>/<code_lowercase>_<descriptive_slug>.py`.
Each file exports one rule via `@register(RuleMetadata(...))`. No central catalog to sync.

### Tests alongside implementation, not after

When you implement a rule, you also create its test file in the same change.
Tests are not a separate phase. A change without tests is incomplete.

### Tests are additive

Don't modify existing passing tests unless their contract genuinely changes.
The test suite is the persistent record of what invariants must hold — a future
agent session has no memory of prior work.

### Fixtures are real Python files

Test fixtures live in `tests/fixtures/` as actual `.py` files. Do not embed
Python source as triple-quoted strings in test files except for one-off cases
not worth a fixture file.

### Reproducibility

Configuration, tier assignment, and rule output are all deterministic. A result
that depends on file ordering, environment variables, or wall-clock time is a bug.

### No imports of analyzed code

docpact must never `import` the code it analyzes. All analysis is static via AST.
Non-negotiable — agents run docpact on code with arbitrary side effects.

### Python version floor

The floor is 3.11. `tomllib` is in stdlib from 3.11; that is the binding constraint.
`match` statements and `importlib.metadata` are fine. PEP 695 `type X = ...` aliases
and generics are 3.12-only — do not use them.

---

## Structural enforcement vs. semantic content

docpact enforces **structure**, not **meaning**. A docstring that passes every
check is not necessarily useful. This distinction matters when generating or
reviewing docstrings.

### What docpact guarantees

- Args section exists and matches the signature (DOC007).
- Required sections are present for the function's tier (DOC012).
- No stale stub markers remain (DOC099).
- Module has a docstring (DOC002).
- No phantom parameters, no silent decorator conflicts.

### What docpact does NOT guarantee

Content quality. This passes all checks:

```python
def process(user_id: str, flags: int) -> dict:
    """Process.

    Args:
        user_id: The user id.
        flags: The flags.

    Returns:
        The result.
    """
```

This is cargo-cult compliance. Every field restates the parameter name.
A coding agent reading this learns nothing beyond what the type annotations
already provide.

Useful docstrings look like this:

```python
def process(user_id: str, flags: int) -> dict:
    """Apply pending transforms to a user account.

    Args:
        user_id: UUID of the user record. Must exist in the user table;
            raises ValueError if not found.
        flags: Bitmask of FeatureFlag values. Unknown bits are silently
            ignored for forward compatibility.

    Returns:
        Snapshot of the account state after all transforms applied,
        keyed by field name. Callers can diff against the prior snapshot
        to determine what changed.
    """
```

### The agent's responsibility

docpact builds the scaffold. The agent fills it with signal. In a
docpact-enabled repo, trust that the structure is correct — then spend
the effort on content that could not be inferred from the signature alone:
preconditions, side effects, invariants, what the return value actually
means, what causes exceptions.

If you generate a docstring with docpact's fix (`--fix`) and it contains
`[FILL]` markers, that is the trigger to write real content. Do not replace
`x: [FILL]` with `x: The x value.` — that is noise, not signal.

---

## Working with Ray

- **Steelman counterarguments before agreeing.** Voice concerns first. Agree plainly
  only after the steelman pass.
- **Surface hidden assumptions explicitly.** Label them as assumptions, not facts.
- **Handle uncertainty rigorously.** Do not guess. Present alternatives explicitly
  and ask which is intended.
- **Red-team your own answers.** For non-trivial responses, include the strongest
  objection if it is substantive.
- **Distinguish empirical from normative.** Flag when a question has a checkable
  answer vs. when it requires a judgment call.
- **No sycophancy, no performed contrarianism.** Disagreement must be earned by
  reasoning. Agreement, when reached honestly, stated plainly.

Conversations are working sessions, not customer support.

---

## Commit message style

- **Subject** ≤70 chars, imperative mood, no trailing period.
  Prefixes: `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`.
  Optional scope: `docs(adr):`, `fix(cli):`.
- **Breaking changes — required, not optional.** Any commit that removes, renames,
  or changes the contract of a public API (CLI flags, config keys, error codes,
  programmatic API) **must** use `!` after the type: `feat!:` or `feat(cli)!:`.
  **Must** also include a `BREAKING CHANGE:` footer paragraph stating what breaks
  and how to migrate. Without both, git-cliff silently omits the entry from the
  Breaking Changes section — the release is published with no warning to users.
- **Body** explains *why*, 72-char wrap. Trade-offs noted.
- `###` headers for multiple unrelated areas; bullets for a single area.
- **No `Co-Authored-By:` trailer.** Every commit is collaborative; the trailer
  is noise. This overrides Claude Code's default — do not add it.

---

## Tooling commands

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
make coverage      # pytest + coverage report (fail_under=85)
make docs          # regenerate docs/rules/*.md from registry
make dogfood       # docpact check src/ (self-check)
make bench         # throughput benchmark vs. local baseline (5% regression threshold)
make bench-update  # save current result as new baseline after intentional changes

# Focused test runs
uv run pytest tests/test_rules/      # rule tests only
uv run pytest -x -k DOC007          # stop on first failure
uv run pytest --lf                   # last-failed only
```

### Releasing

Requires a clean working tree on `main`.

```bash
make release VERSION=0.2.0   # verify → bump files → generate CHANGELOG.md → commit → tag
git push --follow-tags        # triggers .github/workflows/release.yml
```

`make release` updates `pyproject.toml`, `README.md`, and `docs/spec/docpact-spec.md`
atomically via `bump-my-version`, then generates `CHANGELOG.md` from conventional
commits via `git-cliff` (`feat:` and `fix:` only; breaking changes first).
The GitHub Actions release workflow builds, publishes to PyPI, and creates a
GitHub Release with the generated notes.

Type-check suppressions: if `ty check` forces a `# ty: ignore[…]`, justify it
in the commit body. Prefer a narrowing assertion at the call site when it
reflects a real runtime invariant.

---

## Definition of done for a change

1. Code compiles and runs.
2. New code has tests. Modified code has tests covering the modification.
3. `make verify` passes (format + lint + ty + coverage ≥85% + dogfood).
4. New rules have a test file in `tests/test_rules/` and a regenerated entry in
   `docs/rules/` (`make docs`).
5. New public APIs have docstrings that conform to docpact's own schema.
6. Non-trivial decisions not covered by the spec or an existing ADR have a new
   ADR drafted and proposed to Ray.
7. Any breaking change has `!` in the commit subject and a `BREAKING CHANGE:`
   footer. No exceptions — the automated pipeline has no other way to flag it.

---

## What to stop and ask before doing

- **Modifying the spec.** It is the contract. Raise ambiguities explicitly rather
  than picking an interpretation silently.
- **Adding a dependency to `pyproject.toml`.** Every dep is a long-term commitment.
- **Introducing a new architectural pattern.** Needs an ADR and Ray's sign-off.
- **Reordering or renaming error codes.** Stable API — once shipped, never reused.
- **Any breaking public API change without the mandatory commit markers.** Use `!`
  and `BREAKING CHANGE:` footer — see "Commit message style". No exceptions.
- **Adding features beyond the current scope.** See `docs/PROGRESS.md` for what
  is in and out of scope for the current milestone.
- **Changing tier assignment rules.** Deterministic by design. See ADR-003.
- **Changing the file structure.** Documented in `PROJECT_STRUCTURE.md`.

Don't ask permission for routine work — write code, write tests, run `make verify`.
Stop only at the boundaries above.

---

## Common operations

### Adding a new rule

1. Create `src/docpact/rules/<namespace>/<code>_<slug>.py`.
2. Implement with `@register(RuleMetadata(...))`.
3. Add `tests/test_rules/test_<code>.py` — positive, negative, fix, suppression cases.
4. Add fixtures to `tests/fixtures/` if the test benefits from a real file.
5. Run `make docs` to regenerate `docs/rules/<CODE>.md`.
6. Run `make verify`.

### Adding a test fixture

Fixtures live in `tests/fixtures/`. Name by what they demonstrate:
`tier3_missing_constraints.py`, `mcp_decorator_conflict.py`.
Fixtures are excluded from ruff and from docpact's self-check (see `pyproject.toml`).

### Updating the spec (rare)

Do not edit `docs/spec/docpact-spec.md` directly. Open the question with Ray.
Bump the spec version in the header when changes are accepted.

---

## Inbox — unsorted user notes

Quick thoughts are captured as GitHub issues with the `inbox` label.
Pre-triage: one-line remarks to revisit, not bug reports.

**Lifecycle:** open → rejected (closed with reason) or promoted (closed with
link to the relevant work + commit).

**Use `gh` CLI — never the GitHub web UI:**

| Action | Command |
|---|---|
| List open inbox items | `gh issue list --label inbox --state open` |
| Capture (when Ray says "inbox: …" or "note for later: …") | `gh issue create --label inbox --title "[inbox] <60 chars>" --body "<full text>"` |
| Reject | `gh issue close <#> --comment "rejected: <reason>"` |
| Promote | `gh issue close <#> --comment "promoted to <phase/ADR> — see <commit>"` |

Check on demand only — not at session start. When Ray says "inbox: X", create the
issue immediately and acknowledge in one sentence without breaking flow.

---

## ADR process

- A decision warrants an ADR if it is hard to reverse, has cross-cutting
  consequences, or competent engineers might reasonably disagree.
- ADRs are numbered sequentially. Numbers are never reused.
- Use `docs/adr/template.md` as the starting point.
- Status: `Proposed → Accepted → (eventually) Superseded by ADR-NNN`.
- Accepted ADRs are not edited in place. Material changes need a new ADR.

When in doubt about whether to write one, ask Ray.

---

## When stuck

1. Re-read the relevant spec section.
2. Re-read the relevant ADR.
3. Empirical question (checkable)? Find the answer and proceed.
4. Normative question (requires a decision)? Ask Ray with alternatives stated.

Do not silently pick an interpretation and hope it is right.

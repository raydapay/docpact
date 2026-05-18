# ADR-004: Inline suppression comment syntax

**Status:** Accepted  
**Date:** 2026-05-18  
**Deciders:** Ray  
**Related:** spec §15.2 (Inline Suppressions), FIX001 rule, `suppress_comment` config key

## Context

docpact needs a way for authors to suppress specific diagnostics inline, per-line,
without disabling the rule globally. The canonical pattern in Python linting is a
trailing comment on the offending line: `# noqa: CODE`.

The problem: ruff already owns `# noqa`. ruff's RUF100 rule ("unused noqa directive")
removes `# noqa: CODE` comments it cannot match against a known rule. docpact's rule
codes (`DOC001`, `MCP001`, etc.) are unknown to ruff at lint time, so ruff's
auto-fix silently strips valid docpact suppressions.

The workaround is `ruff external = [...]` in pyproject.toml, which tells ruff to
treat listed codes as externally-owned and leave their noqa comments alone. This
works, but it is:

- A list that must be kept in sync by hand as new docpact rules are added.
- Non-obvious to users who don't know ruff's `external` option.
- Fragile: ruff does not guarantee the `external` mechanism is stable across
  versions.

The underlying issue is that two tools are competing for the same comment namespace.
The clean solution is for docpact to own its own namespace.

## Decision

docpact uses `# nodo: CODE` as its default inline suppression comment. The marker
word (`nodo`) is configurable via `suppress_comment = ["nodo"]` in `[tool.docpact]`.
Accepting a list enables side-by-side migration: `["nodo", "noqa"]` matches both
styles during a transition period.

`ruff external = [...]` is removed from docpact's own pyproject.toml. No user of
docpact needs it unless they choose `suppress_comment = ["noqa"]`.

## Rationale

A distinct marker word completely eliminates the namespace collision. ruff never
touches `# nodo` comments. FIX001 (bare suppression without codes) works correctly
regardless of which marker is in use, because `parse_suppressions` is the single
point of authority over what counts as a suppression.

The configurability is justified: some users already have `# noqa: DOC*` comments
in their codebase from before this decision. Forcing an immediate rename of all
existing suppressions is a poor migration story. The list form lets them add `nodo`
first, migrate incrementally, then remove `noqa`.

`nodo` was chosen over alternatives because:
- It is short (4 chars, same as `noqa`).
- It is visually distinct enough that `# noqa` and `# nodo` are not easy to confuse.
- It has no prior meaning in the Python ecosystem.
- It reads plausibly as "no docpact" abbreviated.

## Alternatives considered

### Keep `# noqa` with `ruff external`

The `ruff external` list suppresses RUF100 for listed codes. It works today but is
a maintenance liability: every new rule code must be added to the list, and the
mechanism is undocumented as a stability guarantee in ruff. Rejected because it
couples docpact's user experience to ruff's internals and requires ongoing
synchronisation.

### `# type: ignore`-style embedding (`# nodo: CODE` but inside a `# type: ignore`)

`# type: ignore[code]` is owned by mypy/ty, not a realistic host for docpact codes.
Not seriously considered.

### Per-file or per-function suppression only (no inline syntax)

Possible, but inline suppression is a standard pattern users expect. Removing it
entirely would force noisy config changes for legitimate one-off suppressions. Spec
§15.2 specifies inline suppression as a first-class feature.

### `# docpact: ignore` (verbose form)

More explicit, but `# docpact: ignore: DOC001` is wordy and would be longer than
the lines it annotates in many cases. The short-form convention established by
`# noqa` and `# type: ignore` is correct for this use.

## Consequences

### Positive

- No dependency on ruff's `external` mechanism.
- FIX001 stays correct as rules are added with no synchronisation required.
- Users migrating from `# noqa: DOC*` have a path: configure `["nodo", "noqa"]`,
  migrate files, remove `"noqa"` from the list.
- `suppress_comment` is a general escape hatch if the default ever needs to change.

### Negative

- `# nodo` is not a universally recognised pattern. New users encountering it for
  the first time may not know what it means without reading the docs.
- Any user who wrote `# noqa: DOC*` suppressions before this decision must migrate.
  (No public users yet at the time of this decision.)
- The configurable list adds a small documentation burden: the README and spec must
  describe `suppress_comment` clearly.

### Neutral

- The marker word is lowercased in the comment (`# nodo`) but the rule codes after
  the colon are uppercase (`DOC001`), consistent with `# noqa: CODE` convention.
- `parse_suppressions` builds a dynamic regex from the markers list. Performance
  impact is negligible (compiled once per file, not per line).

## Revisit triggers

- ruff introduces a stable, versioned API for registering external namespaces that
  is guaranteed not to strip unknown `# noqa:` codes — at that point the `external`
  workaround becomes reliable and `# noqa` sharing could be reconsidered.
- A widely-used tool adopts `# nodo` for an unrelated purpose, creating a new
  namespace collision.
- User feedback consistently indicates `# nodo` is too unfamiliar to adopt,
  suggesting the default should change (requires a new ADR).

## References

- ruff `external` option: https://docs.astral.sh/ruff/settings/#lint_external
- ruff RUF100: https://docs.astral.sh/ruff/rules/unused-noqa/
- spec §15.2: Inline Suppressions

# ADR-003: Tier assignment by context, not by per-function configuration

**Status:** Accepted  
**Date:** 2026-05-17  
**Deciders:** [project leads]  
**Related:** Spec §8 (Why Opinionated), §10 (Tier System); ADR-004 (Error code stability), planned

## Context

docpact applies different validation rules to different functions based on tier. A function exposed as an MCP tool is held to a higher documentation standard than an internal helper function. The mechanism that decides which tier a function belongs to has consequences for:

- How predictable validation is for any given function
- How easily a project can be audited for tier compliance
- Whether tier assignment can be circumvented
- Whether rule application is reproducible across machines

The question is: what determines a function's tier?

Two general approaches:

1. **Contextual.** Tier is derived from facts about the function as it appears in source: decorators, naming, class membership.
2. **Annotative.** Tier is declared per-function, by an inline marker, a config file mapping, or a custom decorator.

These can also be combined — context determines a default, annotations override it.

## Decision

**Tier is determined by context: decorator presence, function naming, and containing class. Per-file overrides exist in `[tool.docpact.tiers]` configuration but are visible and auditable. No inline per-function annotations are supported in v0.1.**

The full assignment rules are specified in spec §10.1. The rules are deterministic: given a function's source representation and the project configuration, exactly one tier is assigned.

## Rationale

**Tier should be derivable, not declared.** The audience for a function — internal helper, package-public API, MCP tool — is already encoded in the code structure. An `_`-prefixed name is the Python convention for "internal." A `@mcp.tool` decorator is the explicit declaration of MCP exposure. These signals exist for human and tooling reasons that predate docpact. Reusing them as tier signals avoids inventing a new layer of declaration.

**Reproducibility matters more than flexibility.** If a function's tier can be set anywhere — inline annotation, decorator argument, separate config — then determining which rules apply to a given function requires consulting multiple sources. CI failures become harder to diagnose. Code review becomes harder because the tier may live somewhere other than the function itself. Contextual derivation keeps the answer in one place: the function as it appears in source.

**Inline annotations encourage downgrade abuse.** If a function can declare its own tier via `# docpact: tier=1`, the path of least resistance under deadline pressure is to downgrade. The function that should be Tier 3 gets marked Tier 1 to silence the linter. The contract weakens silently. Removing the option removes the temptation.

**Per-file overrides remain available for legitimate cases.** Some legitimate cases exist where context cannot infer correctly: legacy modules where conventions differ, modules exposing FastAPI routes that are passed to `FastMCP.from_fastapi()` from elsewhere (Tier 4 detection in v0.1), test fixtures. These are handled in `[tool.docpact.tiers]` in `pyproject.toml`. The configuration is checked in and reviewable. The override is visible to everyone, not hidden in a comment in a file.

**Tier rules can evolve without source changes.** Because tier is derived from context, changing the assignment logic (e.g., supporting a new MCP framework, recognizing a new decorator pattern) does not require touching individual function docstrings. The change is one update to docpact, applied uniformly.

## Alternatives considered

### Alternative A: Inline tier annotation via comment

**Description.** Allow per-function tier override via `# docpact: tier=N` on the line above the function.

**Considered because.** It provides escape hatch for edge cases. It is precedented (ruff supports `# noqa`, mypy supports `# type: ignore`).

**Not chosen because.** Tier is a property of the function's role in the codebase, not its individual configuration. Allowing per-function override creates the downgrade-abuse path described above. The `# noqa` precedent applies to suppressing specific rule violations on specific lines, which docpact already supports — that is a different concept from re-categorizing the function entirely.

### Alternative B: Tier declared via decorator argument

**Description.** Functions declare tier via a docpact-specific decorator: `@docpact.tier(2)`.

**Considered because.** Decorators are visible, explicit, and Pythonic. The function carries its own tier marker.

**Not chosen because.** It introduces a new project-specific dependency at the function level. Users would need to `import docpact` in production code to apply tier markers. docpact would gain a runtime API surface it does not need. The contextual signals already present in the code (decorators, naming) carry the same information without adding dependencies.

### Alternative C: Tier as a per-file mapping in configuration

**Description.** Configuration explicitly enumerates every file's tier. No context-based inference.

**Considered because.** It is fully explicit. Every tier assignment is reviewable in one place.

**Not chosen because.** It does not scale. A 500-file codebase requires 500 configuration entries. Adding a new file requires editing configuration. This approach effectively disables tier assignment for the common case where context-based inference is correct.

### Alternative D: Hybrid — context as default, inline annotation as override

**Description.** Use context to derive tier by default, allow inline annotation to override.

**Considered because.** It captures the benefits of context-based inference for the common case while providing escape hatch for edge cases.

**Not chosen because.** Once an inline override mechanism exists, it gets used for cases that should not be overridden. The downgrade-abuse path returns. Per-file configuration overrides handle the legitimate edge cases adequately and force the override into a reviewable location.

## Consequences

### Positive

- Tier assignment is reproducible: the same source code under the same configuration produces the same tier on every machine.
- Code review can verify tier correctness by reading the source, without consulting external config.
- Removing the downgrade-abuse path strengthens the contract enforcement.
- No new runtime dependencies introduced for production code.
- Tier rules can evolve in docpact updates without requiring per-function changes.

### Negative

- Edge cases that do not fit the context-based rules require configuration. Some teams may find this less convenient than inline annotation would have been.
- Detecting cases where context-based assignment is wrong (a function that should be Tier 2 but is being treated as Tier 1) requires examining the rules, not just the function.
- Tier 4 (FastAPI routes via `FastMCP.from_fastapi()`) requires explicit configuration in v0.1 because the relevant context lives at the application assembly site, not at the function. Heuristic detection in v0.2 will reduce but not eliminate this.

### Neutral

- The configuration shape (`[tool.docpact.tiers]`) is fixed in v0.1 and propagates forward.

## Revisit triggers

1. **A pattern of legitimate edge cases emerges that configuration cannot address well.** If many users discover cases where neither context inference nor per-file override is satisfactory, reconsider whether inline annotation is needed.
2. **A new MCP framework or exposure mechanism appears with non-obvious context signals.** Update the tier assignment rules in spec §10.1, document in a new ADR if the change is significant.
3. **Heuristic Tier 4 detection (v0.2, `HEUR` namespace) reveals systematic false negatives in context-based inference.** This would suggest context is insufficient in general and the configuration model should be reconsidered.

## References

1. [PEP 8 — Naming Conventions](https://peps.python.org/pep-0008/#naming-conventions) (specifically the leading underscore convention)
2. Spec §10.1 — full enumeration of tier assignment rules

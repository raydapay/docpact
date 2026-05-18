# Architecture Decision Records

Architecture Decision Records (ADRs) document significant choices made during the design and implementation of docpact. Each ADR captures the context, the decision, the alternatives considered, and the consequences.

ADRs exist alongside the [specification](../spec/docpact-spec.md), not as a substitute for it. The spec describes **what** docpact is. ADRs describe **why** specific choices were made when the spec admits multiple valid answers.

## Process

1. Significant design decisions get an ADR. "Significant" means: the decision is hard to reverse, it has cross-cutting consequences, or competent engineers might reasonably disagree on the answer.
2. ADRs are numbered sequentially. Numbers are never reused, even for retracted ADRs.
3. An ADR's status moves through: `Proposed → Accepted → (eventually) Deprecated | Superseded by ADR-NNN`.
4. Accepted ADRs are not edited in place except for typo fixes and adding `Superseded by` links. Material changes require a new ADR that supersedes the previous one.
5. The [template](template.md) is the starting point for new ADRs.

## Index

| # | Title | Status | Decision summary |
|---|---|---|---|
| [001](ADR-001-implementation-language.md) | Implementation language for v0.1 | Accepted | Python 3.12+ with griffe. Hot-path rewrite to Rust via PyO3 reserved as future optimization. |
| [002](ADR-002-docstring-format-baseline.md) | Docstring format baseline | Accepted | Google style only in v0.1. NumPy in v0.2 via parser abstraction. Sphinx not on roadmap. |
| [003](ADR-003-tier-assignment.md) | Tier assignment by context, not configuration | Accepted | Tiers derived from decorators, naming, and class membership. Per-file overrides exist but are visible in config. |
| [004](ADR-004-suppression-syntax.md) | Inline suppression comment syntax | Accepted | `# nodo: CODE` as docpact's own marker, configurable via `suppress_comment`. Avoids ruff `# noqa` namespace collision. |

## Planned ADRs

These decisions are made in the specification but warrant their own ADR for full rationale capture.

| # | Title | Status |
|---|---|---|
| 005 | Error code stability commitment | Planned |
| 006 | MCP decorator and docstring section mutual exclusion | Planned |
| 007 | Constraints section scope (real-world vs. type-expressible) | Planned |
| 008 | Heuristic rule namespace and severity model | Planned |
| 009 | Configuration file precedence (pyproject.toml vs. docpact.toml) | Planned |

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
| [001](ADR-001-implementation-language.md) | Implementation language for v0.1 | Accepted | Python 3.11+ with griffe. Hot-path rewrite to Rust via PyO3 reserved as future optimization. |
| [002](ADR-002-docstring-format-baseline.md) | Docstring format baseline | Accepted | Google style first; NumPy added via the parser abstraction. Sphinx not on roadmap. |
| [003](ADR-003-tier-assignment.md) | Tier assignment by context, not per-function configuration | Accepted | Tiers derived from decorators, naming, and class membership. Per-file overrides exist but are visible in config. Amended (bounded) by ADR-010 for the `--crossfile` Tier-3 floor. |
| [004](ADR-004-suppression-syntax.md) | Inline suppression comment syntax | Accepted | `# nodo: CODE` as docpact's own marker, configurable via `suppress_comment`. Avoids ruff `# noqa` namespace collision. |
| [005](ADR-005-tool-registry-validation.md) | Same-file tool-registry validation; cross-file registration out of scope | Accepted | `REG` namespace cross-checks same-file `ToolDefinition`/dict registries; cross-file deferred (later opened by ADR-009). |
| [006](ADR-006-interim-architecture-posture.md) | Interim architecture posture — per-file Python, ty as strategic target | Accepted | Stay per-file; veto a hand-rolled module graph; keep griffe (the former ADR-007 was folded in here). Cross-file stance later superseded by ADR-009. |
| 007 | *(withdrawn)* | — | Briefly held the keep-griffe decision; folded into ADR-006 and retired. Number not reused. |
| [008](ADR-008-open-semantic-layer.md) | Open the semantic layer (SEM) with a pluggable LLM backend | Accepted | `docpact semantic` (advisory, opt-in); `LLMBackend` protocol + factory; one openai-compat adapter ships. |
| [009](ADR-009-cross-file-via-lsp.md) | Open cross-file analysis via a provider-agnostic LSP client | Accepted | Opt-in `--crossfile`; resolve imports through an LSP server (default ty); FR-1 REG010. Supersedes ADR-006's cross-file stance. |
| [010](ADR-010-cross-file-tier-floor-and-semantic.md) | Cross-file Tier-3 floor for imported handlers, and cross-file × semantic | Accepted | FR-2(b): imported-handler Tier-3 floor (REG011) + one resolution feeding both `check` and `semantic`. Bounded amendment to ADR-003. |
| [011](ADR-011-call-based-tool-registration.md) | Call-based tool registration — builder-call extraction, indirect descriptions, handler-keyed tier floor | Accepted | Extract configured constructors in non-list positions incl. `register_tool(ToolSpec(...))`; resolve same-file `NAME="..."` descriptions one hop; floor the same-file `handler_ref`. Amends ADR-005. |
| [012](ADR-012-same-file-reg010-default-pass.md) | Same-file REG010 runs in the default pass — model-parity offline | Accepted | REG010 validates same-file `input_model` parity offline in `check` (default-on, `REG010="off"` to disable); cross-file leg still `--crossfile`. Amends ADR-009. |
| [013](ADR-013-module-level-semantic-scan.md) | Module-level semantic scan (SEM002) — model-sensitive, symbols-scoped | Proposed | Build `SEM002` (weak module docstring: scope + orientation), opt-in via `scan_modes=["module"]`, input = docstring + public symbols (no `context_files`). Spike: gpt-4o-mini 71%/43% FP → gpt-4o 0% FP with a consistency-not-completeness prompt. Model-sensitive; weak models not recommended. |

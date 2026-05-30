# ADR-009: Open cross-file analysis via a provider-agnostic LSP client

**Status:** Accepted
**Date:** 2026-05-30
**Deciders:** Ray
**Related:** supersedes ADR-006's cross-file stance (items 2–4, revisit trigger 1, the projected use case); ADR-005 (same-file REG — the cross-file cases it deferred); ADR-008 (the pluggable-backend precedent SEM established); `scripts/spike_lsp.py` (the evidence)

## Context

ADR-005 limited tool-registry validation to **same-file**: cross-file cases (a tool's
`input_model` or handler imported from another module) were out of scope because
correlating them needs a module graph. ADR-006 then set the interim posture —
per-file, and *wait for ty to formalize a stable plugin/semantic-model API* before
attempting cross-file (revisit trigger 1) — while vetoing a hand-rolled resolver
(false-positive tar pit).

A realization reframes that wait: **ty — and every serious Python type checker —
speaks the Language Server Protocol**, a versioned, stable, editor-agnostic standard.
The stable cross-file interface docpact was waiting for is not a bespoke ty API; it
already exists, as LSP.

A spike (`scripts/spike_lsp.py`) settled the one empirical unknown — *does
`textDocument/definition` actually resolve the patterns that matter?* It drove
`ty server` over stdio and resolved an imported symbol used as a **call kwarg value**
(`input_model=SearchTransactionsInput`) to its true class definition in two scenarios:
direct import, and a **re-export chain** (`tools` → `pkg/__init__` → `pkg/schemas`).
Both resolved to the real definition file, statically (ty executes nothing).

The question: **open cross-file analysis now, and on what mechanism?**

## Decision

**Open cross-file analysis as an opt-in capability backed by a provider-agnostic LSP
client.**

1. **LSP client, not a resolver.** docpact spawns a language server, and asks it
   `textDocument/definition` (and where useful, `hover`/`typeDefinition`) to resolve
   an imported symbol to its **defining file**. docpact then does its **own AST
   extraction** on that file (reusing DOC050's model-field logic / signature parsing).
   The server does resolution; docpact does everything else.
2. **Provider-agnostic.** The server is configured (`[tool.docpact.lsp]`, command +
   args), defaulting to ty. Any LSP-conformant server — pyright, pylsp, jedi — is a
   drop-in swap. docpact depends on the *protocol*, not on ty. If ty is abandoned,
   change one config line.
3. **Opt-in, optional dependency.** Cross-file analysis runs only when enabled and a
   server is available (`docpact[crossfile]` extra, or a user-provided server command).
   The default per-file `check` is unchanged — offline, dependency-free, fast.
4. **Deterministic.** Unlike SEM, LSP resolution is reproducible (same code → same
   definition). With a pinned server it can back a deterministic check, not merely an
   advisory one. It stays **static** — the server resolves without executing code, so
   docpact's no-import/no-execution guarantee holds.
5. **Delivers the deferred cross-file cases:** FR-1 (Args block ↔ imported Pydantic
   model fields) and FR-2(b) (imported-handler signature correlation) — the
   "replace our bespoke contract test" capability.
6. **The hand-rolled module graph stays vetoed** (ADR-006); this is the "consume an
   existing resolver" path, now concrete.

This **supersedes** ADR-006's cross-file deferral (items 2–4), its revisit trigger 1
("wait for ty's API"), and the projected-use-case section — the wait is over, the
interface is LSP. ADR-006's per-file *default*, parallelism (item 5), and griffe
decision (item 6) are unaffected.

## Rationale

**LSP is the stable interface we were waiting for.** ADR-006 framed trigger 1 as
"ty formalizes a stable public API." LSP is exactly that — standardized, versioned,
and already implemented by ty (spike-verified). Waiting for a *bespoke* ty API was the
wrong gate; the standard one is live.

**Provider-agnosticism is the durable bet.** Reusing existing tools through their
standard protocol is how robust tools compose. docpact speaking LSP means it inherits
the entire ecosystem of Python language servers, present and future, with no lock-in
to any one vendor — the same pluggability win ADR-008 chose for the SEM backend.

**Static + deterministic.** The server resolves by static analysis (no execution), so
the no-execution guarantee survives; and resolution is reproducible, so a pinned-server
cross-file rule can be check-grade rather than advisory.

**Measured before deciding.** Per the project's measure-first discipline, the spike
proved resolution works on the *realistic* shape (kwarg-value reference + re-export
chain), not a toy — before committing to the subsystem.

## Alternatives considered

### Alternative A: hand-rolled Python module graph

**Rejected (unchanged from ADR-006).** Reimplements the resolver — the false-positive
tar pit. LSP delegates it to a tool that does it correctly.

### Alternative B: wait for a bespoke ty plugin/semantic-model API

**Rejected.** It may never come, and it isn't needed: LSP is the stable interface, and
binding to a ty-specific API would forfeit the provider-agnosticism that protects us if
ty stalls or is abandoned.

### Alternative C: griffe static loader (the ADR-006 "deep mode")

**Now moot.** griffe could resolve imports statically too, but it ties us to one
library and its resolution semantics; an LSP client is server-swappable and reuses a
purpose-built type checker. LSP is the better realization of the same idea.

### Alternative D: stay deferred

**Rejected** on evidence: the spike shows it works on the real pattern, and this is the
highest-value adopter request ("replace our contract test").

## Consequences

### Positive

- Unlocks deterministic cross-file tool-contract checking (FR-1, FR-2(b)) — the killer
  adopter capability — without building a resolver.
- Provider-agnostic: ty today, any LSP server tomorrow; no vendor lock-in.
- Preserves the no-execution guarantee (LSP servers resolve statically).
- The default per-file `check` is untouched: offline, dependency-free, deterministic.

### Negative

- A new subsystem: an LSP client (server lifecycle, JSON-RPC over stdio,
  `Location`/`LocationLink` normalization, graceful degradation when no server is
  installed).
- An optional heavy dependency (a language server), version-coupled to its resolution
  behavior; cross-file results are only as good as the chosen server.
- Per-symbol queries + workspace-index startup — fine for an opt-in cross-file pass,
  not for folding into every `check`.

### Neutral

- `[tool.docpact.lsp]` config shape is introduced by the implementation.
- Cross-file rules' code/namespace are decided at build time (this ADR is the
  direction; the build follows).

## Revisit triggers

1. **A chosen server's resolution proves flaky at scale** (re-export edge cases,
   dynamic patterns) → tighten scope, document the gap, or recommend a different server.
2. **LSP-client startup/query latency is unacceptable** even for an opt-in pass →
   reconsider batching or a persistent-server daemon.
3. **A lighter, stable, non-LSP resolution API appears** (from ty or elsewhere) that is
   clearly better → re-evaluate; the AST-extraction half is reusable regardless.

## References

1. `scripts/spike_lsp.py` — the spike (direct + re-export, kwarg-value reference) that cleared the bar
2. ADR-006 — interim posture (this ADR supersedes its cross-file stance only)
3. ADR-005 — same-file REG; the cross-file cases this ADR addresses
4. ADR-008 — pluggable backend precedent (SEM); same provider-agnostic philosophy
5. LSP specification — https://microsoft.github.io/language-server-protocol/ ; ty language server — https://docs.astral.sh/ty/features/language-server/

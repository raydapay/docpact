# ADR-012: Same-file REG010 runs in the default pass — model-parity offline

**Status:** Accepted
**Date:** 2026-05-31
**Deciders:** Ray
**Related:** amends ADR-009 (item 5 — REG010 was delivered as cross-file-only); ADR-005 (same-file REG posture); ADR-011 (call-based extraction + indirect descriptions, which this builds on for the same adopter); spec §15.3 (REG rule contracts); originating adopter feedback (ask #3 — "same-file shouldn't need the `[crossfile]` extra")

## Context

REG010 checks parity between a tool entry's documented `Args:` keys (parsed from its
description) and its `input_model`'s actual fields. ADR-009 shipped it as a
**cross-file** rule: it runs only under `docpact check --crossfile`, resolves the
`input_model` symbol to its defining file via the LSP server, and then extracts the
model's fields by docpact's own AST pass. The resolver is needed because the model may
be *imported* from another module.

But a large share of real surfaces define the `input_model` in the **same file** as
the registry entry (the adopter's `DescribeProviderInput` sits beside its `ToolSpec`).
For that case the LSP buys nothing: the model class is a `class <Name>` in the same
AST docpact has already parsed. Yet today the same-file case still requires the
`[crossfile]` extra, a configured server, and the `--crossfile` flag — the hard
machinery for the easy case. The adopter put this plainly: requiring a cross-file
import (and thus the LSP) to validate same-file parity is a surprising limitation;
same-file is the easier case and shouldn't need the extra at all.

This is the inverse of ADR-005's own framing. ADR-005 established that same-file
correlation is the cheap, offline, no-module-graph case and made it the default; ADR-009
opened the genuinely cross-file cases behind an opt-in resolver. REG010's same-file
leg was folded into the cross-file pass for implementation convenience, not because
it needs a resolver. ADR-011 sharpens the point: once call-based entries are extracted
and indirect descriptions resolved, the adopter's REG010 inputs (documented Args keys,
a same-file `input_model` class) are *all present in one AST* — and still nothing fires,
solely because the rule is gated on `--crossfile`.

The question this ADR answers: **should REG010 validate same-file model parity in the
default, offline `check`, and if so, is that change safe to default on?**

## Decision

**REG010 gains a same-file leg that runs in the default per-file pass, default-on
whenever `REG` is selected.**

1. **Same-file leg (new, offline).** When an entry's `input_model_ref` resolves to a
   `class <Name>` **defined in the same file**, docpact extracts that class's fields
   by its existing AST model-field pass (the same logic ADR-009 reuses, sourced from
   the local module instead of an LSP-resolved file) and runs the Args↔fields parity
   check in the per-file pass — no server, no `--crossfile`, no `[crossfile]` extra.
   The same-file class must be unambiguous: if the `input_model` name is an *imported*
   symbol (no same-file `class` of that name), the same-file leg does not fire and the
   case falls through to the cross-file leg.

2. **Cross-file leg (unchanged).** When the `input_model` is imported from another
   module, REG010 behaves exactly as ADR-009 specified: it runs only under
   `--crossfile`, resolves via the LSP server, and degrades gracefully if no server is
   available.

3. **Contract unchanged; reach extended.** REG010 still means "documented Args ↔
   `input_model` fields parity," still WARNING, still fires only when the description
   parses to a static set of Args keys and the model fields are statically known. Only
   its *reach* extends to the same-file case. It remains gated on `REG` being in
   `select`.

4. **Default-on, with the standard off-switch.** A project that does not want same-file
   REG010 sets `REG010 = "off"` under `[tool.docpact.rules]` — the existing per-rule
   severity mechanism. This is classified `feat:`, not a breaking change: no flag,
   config key, or error code is removed or redefined. Because it can surface new
   WARNINGs on upgrade for projects treating warnings as CI failures, the change is
   called out prominently in CHANGELOG.

## Rationale

**Same-file is the easier case and belongs in the offline pass — this restores the
ADR-005 split.** docpact's architecture is "same-file is offline-by-default; cross-file
needs a resolver" (ADR-005, ADR-009). REG010's same-file leg sitting behind
`--crossfile` inverts that for no reason other than where the code happened to live.
Moving it is closer to fixing a rule that silently no-op'd on same-file models than to
changing a contract: an adopter with a same-file `input_model` got *nothing* from
REG010 unless they installed a language server to resolve a symbol that was never
cross-file.

**The resulting asymmetry is principled, not arbitrary.** After this change REG010
fires same-file in plain `check` but needs `--crossfile` for imported models. That is
exactly the project's core boundary, applied per-leg: docpact does same-file work
offline and delegates cross-file resolution to a server. We own this explicitly in the
rule doc and CHANGELOG so it reads as the architecture, not an accident.

**Default-on is right, and reversible in one line.** REG is fully opt-in, REG010 is a
WARNING, and `extract_tool_registry` is `Stability: beta` — the bar for "never emit a
new finding on upgrade" is a 1.0 bar, and docpact is at `0.1.0a`. Same-file parity is
high-signal and low-false-positive: it compares a statically-parsed set of Args keys
against a statically-extracted set of model fields, both literal, both same-file. A
project surprised by new warnings disables the rule with the standard
`REG010 = "off"`. Gating it behind a *new* opt-in instead would merely swap
`--crossfile` friction for a different flag's friction — re-creating the very
"configure something extra to get any value" complaint that motivated the change.

## Alternatives considered

### Alternative A: keep REG010 cross-file-only (status quo)

**Considered because** it is the shipped behavior and requires no change; ADR-009
already delivers REG010 for anyone who runs `--crossfile`.

**Not chosen because** it makes the *easy* case (same-file model) require the *hard*
machinery (server, extra, flag) — the exact surprise the adopter reported. It leaves
REG010 a silent no-op for offline runs over same-file surfaces, which is most of them.

### Alternative B: same-file REG010 behind a new opt-in flag/select

Add a flag (or require `--extend-select`) to enable the same-file leg.

**Considered because** it is the most conservative on upgrade — no project sees new
warnings without asking.

**Not chosen because** REG010 is already gated on `REG` being selected, and a per-rule
off-switch already exists; a second gate adds friction without adding safety the
off-switch doesn't already provide. It re-introduces the "need a special flag to get
value" friction the adopter is asking us to remove.

### Alternative C: run the whole of REG010 (including cross-file) in the default pass

Drop the `--crossfile` gate entirely and resolve imported models in plain `check`.

**Not chosen because** the cross-file leg genuinely needs the resolver — it cannot run
offline. Folding a language-server dependency into every `check` violates ADR-009's
"default `check` is offline, dependency-free, fast" guarantee. The split — same-file
offline, cross-file under `--crossfile` — is the whole point.

## Consequences

### Positive

- REG010 delivers its value for same-file surfaces in plain `docpact check` — no
  server, no extra, no flag. Combined with ADR-011, the adopter's contract check works
  fully offline.
- Restores the ADR-005 same-file/cross-file split for REG010, removing an
  implementation-driven inversion.
- High-signal parity drift (documented Arg with no model field, or vice versa) is
  caught in the default pass where most runs happen.

### Negative

- Projects that select `REG`, have same-file `input_model` entries, and carry an actual
  parity drift will see new WARNINGs on upgrade — a CI red for anyone treating warnings
  as errors until they fix the drift or set `REG010 = "off"`.
- REG010 now has two code paths (same-file AST extraction, cross-file LSP resolution)
  to keep behaviorally consistent — a maintenance cost.

### Neutral

- The same-file/cross-file asymmetry in *when* REG010 fires becomes a documented part
  of the rule's contract.
- Field extraction logic is shared between the two legs; only the source file (local
  vs. LSP-resolved) differs.

## Revisit triggers

1. **Same-file class resolution proves ambiguous** (a name bound to both a same-file
   `class` and an import, conditional/redefined classes, re-exports) producing
   false-positive parity findings → tighten the same-file resolution rule or defer the
   ambiguous case to the cross-file leg.
2. **Default-on causes broad upgrade churn** across adopters beyond the expected small
   intersection → reconsider gating (Alternative B) for a major release.
3. **A non-LSP same-file model-field source is needed** (e.g. dataclasses, attrs,
   TypedDict beyond the current Pydantic extraction) → extend the shared field
   extractor, not this gate.

## References

1. ADR-009 — cross-file via LSP (amended here: item 5, REG010's delivery scope)
2. ADR-005 — same-file REG posture (the split this restores for REG010)
3. ADR-011 — call-based extraction + indirect descriptions (supplies REG010's inputs
   for the call-based adopter)
4. Spec §15.3 — REG rule contracts
5. Originating request — adopter feedback ask #3 (same-file should not require the
   `[crossfile]` extra)

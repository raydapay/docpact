# ADR-010: Cross-file Tier-3 floor for imported handlers, and cross-file × semantic composition

**Status:** Accepted
**Date:** 2026-05-31
**Deciders:** Ray
**Related:** extends ADR-009 (cross-file via LSP — this is its FR-2(b) half); amends ADR-003 (tier assignment determinism); builds on ADR-005 (same-file REG + the same-file Tier-3 floor) and ADR-008 (semantic layer); touches spec §10.1 (tier assignment), §12.2 (semantic), §15.

## Context

ADR-009 opened cross-file analysis via an LSP client and shipped **FR-1** (a
tool's documented `Args:` ↔ its imported `input_model` fields, REG010). It named
**FR-2(b)** — *imported-handler correlation and the cross-file Tier-3 floor* — as
in scope but deferred, flagging it "genuinely harder" and "reverse-direction."

The hardness is structural. ADR-005's same-file Tier-3 floor is easy: a registry
entry and the function it names live in the same file, so the floor is applied
during that file's check. But when a registry in module **A** registers a handler
imported from module **B**:

```python
# A/registry.py
from B.handlers import search_cases
TOOLS = [ToolDefinition(name="search", handler=search_cases, input_model=SearchInput)]
```

the fact that makes `search_cases` agent-facing lives in **A**, while the function
being checked lives in **B**. B's own file gives no hint. A file-local tier
assignment (spec §10.1) cannot see it.

Separately, two capabilities already resolve/scan functions but cannot see across
files: `docpact semantic` (ADR-008) scopes by **file-local** `assign_tier` and
prompts the LLM with only `signature + docstring` — so it both *misses* imported
agent handlers entirely and, even for tools it does see, judges a *fragment* of a
contract whose real parameters are defined in another module.

Two questions: **(1)** how should an imported handler be held to the Tier-3 bar,
given the floor fact is in another file? **(2)** how should the deterministic
cross-file resolution and the advisory semantic layer compose?

## Decision

**Open FR-2(b) as a cross-file pre-pass that feeds tier assignment, and make
cross-file resolution a shared context provider consumed by both the
deterministic rules and the semantic layer.**

1. **Handler reference capture.** Extend registry extraction (as ADR-009 Step 2
   did for `input_model`) to also capture a `handler` reference — a bare `Name`
   in the configured handler field — with its source position. Backward-compatible.

2. **`--crossfile` becomes a pre-pass, not a post-pass.** One LSP session, run
   *before* the per-file checks, resolves every `input_model` and `handler`
   reference across the project and produces three things: (a) a **handler floor
   map** `{(defining-file, def-line) → 3}`; (b) FR-1 findings (REG010); (c) the
   handler-signature parity findings (REG011, a later increment).

3. **The floor raises the tier; the existing rule engine does the rest.** The
   floor map is threaded into per-file tier assignment so a floored function's
   tier becomes `max(3, t)`. No new "tier-3-lite" rule path: the function is held
   to Tier 3 by the *same* DOC012/etc. rules every Tier-3 function obeys, yielding
   precise findings ("missing Constraints/Stability/MCP") rather than one coarse
   diagnostic.

4. **Tier assignment becomes project-level deterministic under `--crossfile`,
   not file-level.** This is an explicit, bounded amendment to ADR-003: a
   function's tier may now depend on another file (and on the pinned LSP server's
   resolution) **only when `--crossfile` is passed**. The default `check` is
   unchanged — file-local and offline. Determinism holds: same project + same
   pinned server → same tiers. What changes is the *unit* of determinism (project,
   not file). `check B.py` and `check src/ --crossfile` may legitimately assign
   `search_cases` different tiers; that divergence is the honest meaning of
   "this function is more important than B-alone reveals."

5. **Cross-file × semantic: one resolution, two consumers.** The same resolved
   facts feed both sides — deterministic *structure* and advisory *meaning*:
   - **Scope:** `docpact semantic --crossfile` runs the floor pre-pass, so
     imported handlers promoted to Tier 3 enter `--min-tier` scope (today they
     are invisible to it).
   - **Context:** the resolved `input_model` fields and the registry description
     are injected into the SEM prompt, so the LLM judges the *complete* contract
     ("does this handler's docstring explain the imported model's fields, or just
     restate names?") rather than the local fragment.
   The division of labour is clean: REG010/REG011 check whether the names line up
   (structure); SEM judges whether the prose means anything (meaning), on the same
   resolved data.

6. **Graceful degradation is unchanged (ADR-009).** A handler the server cannot
   resolve simply does not receive the floor — docpact **under-enforces** rather
   than inventing a Tier-3 demand it cannot justify. A missing/failing server
   degrades to a clear note; the run continues.

**Sequencing (decided):** increment 1 ships handler capture + the floor + the
semantic composition (scope + prompt context); REG011 (handler-signature parity)
follows as increment 2.

## Rationale

**Reuse the rule engine, don't fork it.** Once a handler is correctly identified
as Tier 3, the project already has a precise, tested definition of what Tier 3
requires. Raising the tier and letting DOC012 et al. run is less code and far more
precise than a bespoke "registered-but-underdocumented" diagnostic that would
re-implement a slice of the tier rules in prose.

**The determinism amendment is honest, not a regression.** ADR-003's file-local
guarantee was correct for a per-file tool. Cross-file analysis is, by definition,
not per-file; pretending a registered handler's importance is knowable from its
own file would be the actual error. Confining the amendment to `--crossfile`
keeps the strong, simple guarantee for the default path and makes the weaker
(project-level) guarantee opt-in and explicit.

**Composition multiplies value at near-zero marginal cost.** The expensive part —
spinning up a server and resolving references — already happens for REG010. Having
SEM consume the same resolution is mostly plumbing, and it removes SEM's two
blind spots (missed handlers, fragmentary contracts) that no per-file pass can fix.

**Pre-pass is forced by the floor, and it is also cleaner.** The floor must be
known before tier assignment, so resolution must move ahead of the per-file pass.
That one move also collapses REG010/REG011/floor into a single LSP session instead
of several.

## Alternatives considered

### Alternative A: dedicated diagnostic, tier left untouched

Emit a single cross-file finding ("registered as a tool in A, documented below the
Tier-3 bar") and never change a function's tier, preserving ADR-003's file-local
invariant. **Rejected.** It buys invariant-purity at the cost of precision: it
either restates the Tier-3 rule set in one message or points vaguely at "below the
bar." Re-tiering reuses the real rules and the real findings. The invariant it
protects is, for cross-file work, the wrong invariant.

### Alternative B: scope-only semantic integration

`semantic --crossfile` runs the floor (so handlers are in scope) but leaves the
prompt as signature + docstring. **Rejected as the target**, though it is the
natural first slice: it fixes the *missed-handler* blind spot but not the
*fragmentary-contract* one, which is where the cross-file signal is most valuable
to an LLM judge. We ship both together (the decided depth).

### Alternative C: fold handler-signature parity (REG011) into REG010

Use one rule for both "Args ↔ model" and "handler signature ↔ schema." **Rejected.**
They are distinct checks against distinct sources (documented prose vs. the
function signature) and should be independently selectable/suppressible, the same
way REG001 and REG002 are split. Distinct code, sequenced second.

### Alternative D: stay deferred (ship only FR-1)

Leave FR-2(b) unbuilt. **Rejected** on the adopter value: the imported-handler
pattern is exactly the "central registry module" case ADR-005 called the
highest-value cross-file target, and the floor is what makes `check` and
`semantic` enforce the agent-facing bar on the functions that actually need it.

## Consequences

### Positive

- Imported agent handlers are held to the Tier-3 documentation bar by the full,
  existing rule set — the declarative replacement for hand-written contract tests.
- `semantic` finally sees the right functions and judges the whole contract;
  deterministic structure and advisory meaning compose on one resolution.
- One LSP session per `--crossfile` run does all cross-file work.

### Negative

- Tier assignment is no longer file-local under `--crossfile` (bounded ADR-003
  amendment). A reader must know that a single-file check and a project crossfile
  check can tier the same function differently.
- `--crossfile` restructures from post-pass to pre-pass: the floor map must be
  computed before, and threaded (picklably) into, the parallel per-file workers.
- `semantic --crossfile` gains a deterministic LSP dependency on top of its
  network dependency (both opt-in).

### Neutral

- New config: a `handler_field` under `[tool.docpact.registry]` (default
  `"handler"`). REG011 is a new reserved-then-shipped code.
- Spec §10.1 gains a note on the cross-file floor; §12.2 a note on `--crossfile`
  semantic context.

## Revisit triggers

1. **The project-level tier divergence confuses adopters** (e.g. CI tiers a
   function differently than a local single-file check) → consider surfacing the
   applied floor explicitly in output, or a `--explain-tier` affordance.
2. **Pre-pass latency dominates** an opt-in `--crossfile` run on large trees →
   batch/parallelize resolution, or cache the floor map across runs.
3. **Handler references are routinely non-`Name`** (decorated registration,
   partials, factory calls) → widen capture beyond bare `Name`, or document the gap.
4. **Prompt-injected cross-file context degrades SEM precision** (more tokens, more
   noise) → make the enrichment a toggle, or scope it to the model fields only.

## References

1. ADR-009 — cross-file via LSP (FR-1 shipped; this ADR is its FR-2(b) half)
2. ADR-005 — same-file REG and the same-file Tier-3 floor this generalizes
3. ADR-003 — tier assignment determinism (amended here, bounded to `--crossfile`)
4. ADR-008 — the semantic layer this composes with
5. spec §10.1 (tier assignment), §12.2 (semantic), §15 (configuration)

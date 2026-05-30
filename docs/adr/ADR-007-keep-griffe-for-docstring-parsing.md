# ADR-007: Keep griffe for docstring parsing — reimplementation not justified

**Status:** Accepted
**Date:** 2026-05-30
**Deciders:** Ray
**Related:** ADR-001 (griffe chosen as docstring foundation); ADR-006 (interim posture — this ADR supersedes its "griffe removal is desired but unscheduled" note); PROGRESS.md "Performance baseline (2026-05-30)"

## Context

docpact depends on griffe (`>=1.5,<2.0`) for one thing: Google/NumPy docstring
*section* parsing in `parser/docstring.py`. That is its only real consumer — the
other griffe mentions in the codebase are comments. griffe is one of just three
runtime dependencies (with click and rich).

A case to drop it accumulated:

- We use a thin slice — ~6 of griffe's 25+ section kinds (text, parameters, raises,
  returns, examples, admonition) — and run it in a degraded mode: we construct
  `griffe.Docstring(cleaned)` with no parent, so its signature-coupling is dead
  code for us; we disable its warnings; we discard its expression-compiled
  annotations (we `str()` them). We also already maintain ~200 LOC of adapter
  (`_sections_from_griffe`, regexes, admonition map) whose only job is translating
  griffe's rich model back into our flat `ParsedDocstring`.
- We import it via `griffe._internal.docstrings.google` — an internal module path —
  and pin `<2.0`, so a griffe 2.0 is a forced future migration.
- Dropping it would leave a near-dependency-free core (click + rich), aid the
  port-readiness goal in ADR-006, and let us own our own narrow docstring grammar.

A reimplementation — even a Rust state machine for the indentation block-reader,
which has a clean string→struct FFI boundary — was seriously considered.

The question: **reimplement/drop griffe, or keep it?**

## Decision

**Keep griffe. Do not reimplement docstring parsing, in Python or Rust.** The
dependency is acceptable as-is.

This decision was gated on measurement, not intuition (see Rationale). It supersedes
the ADR-006 Neutral note that framed griffe removal as "a desired but unscheduled,
standalone task": removal is **not** desired at this time and is **not** scheduled.

## Rationale

**The perf premise was disproven by measurement.** The reimplementation case had
quietly come to rest on a belief that griffe was "the heaviest per-function cost."
Direct instrumentation of a serial run over docpact's own 51-file / 164-function
corpus (median of 15 runs) says otherwise:

| Stage | Share of runtime |
|---|--:|
| rules + dispatch + everything else | 68% |
| `extract_functions` (AST + FunctionInfo) | 22% |
| `parse_suppressions` (tokenize) | 8% |
| **docstring parse (griffe)** | **3%** |

griffe is ~3% of runtime. Removing it — by any means — saves on the order of 5 ms
on a 250 ms run. Every non-trivial reason to do the work therefore has to stand
*without* a performance argument, and none is strong enough:

- **Pure-Python reimplementation:** ~+200 LOC of parser we own forever, plus real
  regression risk on griffe's genuinely fiddly indentation/continuation/blank-line
  state machine (the ~90-line core that is hardened against a far larger corpus
  than our test net), to shed one dependency and ~5 ms. Cost/risk exceeds benefit.
- **Rust extension:** optimizes 3% of runtime at the cost of the entire distribution
  apparatus (maturin, a cibuildwheel matrix across platforms × Python versions, a
  Rust toolchain in CI, the end of pure-Python `pip install`, a permanent
  two-language codebase). A clearly bad trade. A sharper observation also applies:
  **the cleanly-extractable component is not the slow one.** The docstring parser
  has the nicest FFI boundary in the codebase but is 3%; the actual hot paths (the
  rule loop, AST extraction) have no clean boundary and are the "rewrite in Rust"
  path ADR-006 reserved, not a surgical extension. "Nice to extract" and "worth
  extracting" point at different code.

**griffe is cheap to keep.** It is isolated to one file behind the `DocstringParser`
Protocol, battle-tested on a large real-world docstring corpus, and stable. The
`<2.0` pin means today's behavior is frozen until we choose to move. "It works, it's
3%, it's isolated, leave it" is the honest reading of the data.

**Measure-first paid off.** Had we written the reimplementation plan first (as was
nearly done), we would have spent a day-plus reimplementing a hardened parser to
optimize 3% of runtime. Measuring before building turned a plausible-sounding plan
into a clear no. That discipline — verify the bottleneck before optimizing it — is
the durable lesson here.

## Alternatives considered

### Alternative A: Pure-Python reimplementation of the section parser

**Considered because.** Sheds a dependency, removes the `<2.0` migration liability,
deletes ~200 LOC of adapter, and lets docpact own its narrow grammar. Behind the
existing Protocol with a 50-test net + griffe-as-oracle differential testing, it was
de-riskable.

**Not chosen because.** At 3% of runtime the benefit is dependency hygiene only, and
that does not outweigh ~200 LOC of permanently-owned parser plus regression risk on
the fiddliest part of docstring parsing. Reversible later if the calculus changes.

### Alternative B: Rust extension for the docstring state machine

**Considered because.** Pure string→struct, clean FFI boundary, GIL-release would
let the hot fraction parallelize with threads, and it would be a low-blast-radius
Rust toe-in-water aligned with the eventual ty/Rust direction.

**Not chosen because.** It optimizes 3% of runtime while importing the full
build/distribution cost of a compiled extension — strictly bad value. And it targets
the wrong code: the slow paths are not cleanly extractable. Hard no on current data.

### Alternative C: Keep griffe (chosen)

**Why.** Isolated, stable, battle-tested, 3% of runtime, pinned. No churn, pure-Python
install preserved. The cost of keeping it is lower than the cost of replacing it.

## Consequences

### Positive

- No churn, no regression risk; docpact stays pure-Python and `pip install`-able
  anywhere with no build step.
- Docstring edge cases stay covered by griffe's hardened parser rather than our
  smaller test net.
- Engineering attention is freed for things that aren't 3% of runtime.

### Negative

- We continue to carry a dependency we use ~6% of, imported via an `_internal`
  module path, pinned `<2.0` — so a griffe 2.0 remains a future forced migration.
- The ~200 LOC of griffe-to-`ParsedDocstring` adapter glue stays.
- The port-readiness goal (ADR-006) is marginally worse off: a future ty/Rust move
  would still have to deal with griffe. Accepted as a small, later cost.

### Neutral

- The `DocstringParser` Protocol remains the swap point, so this decision is cheaply
  reversible if a revisit trigger fires.

## Revisit triggers

1. **griffe 2.0 forces a migration that costs as much as reimplementing.** If the
   `<2.0` → 2.0 move is non-trivial, re-evaluate A (reimplement) vs. paying the
   migration — at that point the reimplementation's relative cost has dropped.
2. **griffe becomes unmaintained, or its `_internal` API breaks under us.** Reopen A.
3. **A profiler shows docstring parsing has become a material share of runtime**
   (e.g. a rule starts re-parsing, or corpus characteristics change). Unlikely, but
   it would restore a perf argument.
4. **A Rust rewrite of docpact happens for other reasons (the ty path).** Then griffe
   falls out naturally and this ADR is moot — not a reason to act now.

## References

1. ADR-001 — why griffe was chosen for docstring parsing
2. ADR-006 — interim architecture posture (this ADR supersedes its griffe-removal note)
3. PROGRESS.md — "Performance baseline (2026-05-30)" (the measurement behind this decision)

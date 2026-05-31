# ADR-013: Module-level semantic scan (SEM002) — model-sensitive, symbols-scoped

**Status:** Proposed
**Date:** 2026-06-01
**Deciders:** Ray
**Related:** ADR-008 (opened the SEM layer; listed module-level scan as designed-not-built — this is its build decision); spec §12.2 (semantic design), §15.1 (`scan_modes`); `scripts/spike_semantic_module.py` (the evidence)

## Context

`SEM001` judges *function* docstrings against their signatures. Module docstrings
are unchecked for meaning: `DOC002` guarantees a module docstring *exists*, but
nothing judges whether it is *useful* — the same structure-vs-meaning gap SEM001
fills for functions. A coding agent navigating a repo reads module docstrings to
decide which module to import from or edit; a generic or stale one misleads it.

ADR-008 listed module-level scan as **designed, not yet built**, and set the
project's discipline: a semantic feature ships only after a spike proves the LLM
signal is real and low-false-positive (the function-level spike cleared 26/26).
This ADR records the module-level spike and the build decision it produced.

The spike (`scripts/spike_semantic_module.py`) measured false-positive rate on 12
of docpact's own (deliberately well-written) module docstrings and recall on 3
planted-bad cases, across input variants (docstring alone / + public symbols / +
project context) and two rubric dimensions (scope, orientation).

**The first result said "don't build."** `gpt-4o-mini` with a first-draft prompt
produced **71% scope FP and 43% orientation FP** on known-good docstrings. The
failure was diagnostic: the prompt said the docstring should not "omit the main
purpose" and handed the model the symbol list, so the model demanded the docstring
*enumerate* its public symbols — flagging good docstrings for "omits `LSPClient`",
"omits `resolve_crossfile`". That is pedantry, not drift.

**Removing two confounds reversed it.** A hardened prompt (judge *consistency*,
never *completeness*; "NEVER flag for omitting or under-listing symbols") on
**`gpt-4o`** produced **0/12 FP on both dimensions, stable across two runs**, with
full recall: each planted-bad case was caught by exactly the right dimension
(domain-mismatch → scope; boilerplate → orientation). The `symbols` input variant
was sufficient — the project-`context` variant was not needed for either
dimension.

The question this ADR answers: **build module-level semantic scan, and if so with
what rubric, what input, and what guardrails against its model sensitivity?**

## Decision

Build **`SEM002` — weak module docstring**, advisory and opt-in, mirroring SEM001's
posture (never in `check`; non-deterministic; behind `docpact semantic`).

1. **New code `SEM002`**, not a `scan_modes` flavour of `SEM001`. The unit
   (a module vs a function), the rubric, and the verdict vocabulary all differ;
   reusing SEM001's code would overload a stable error code (spec §18.1).

2. **Rubric — two dimensions, each judged independently, both validated at 0 FP:**
   - **scope** — is the docstring's stated purpose *consistent* with the module's
     actual public symbols? Weak only when it describes a capability/domain the
     symbols do not support, or names a symbol that does not exist. **Consistency,
     never completeness:** a docstring that describes the purpose accurately is
     good even if it names no symbol. Omitting / under-listing symbols is never a
     defect — this clause is load-bearing; without it the FP rate is 71%.
   - **orientation** — is the docstring contentful, or pure boilerplate ("Utilities.",
     "The widgets module.")? Weak only for near-empty restatement; never for
     brevity, for not comparing to siblings, or for not spelling out when to use it.

3. **Input = module docstring + its public symbols** (top-level non-`_` defs/classes
   with their summary lines). **No `context_files`.** The spike's `symbols` variant
   reached 0 FP without project context; the designed `context_files` plumbing is
   therefore *not* built for SEM002. (It remains reserved for a future dimension
   that genuinely needs sibling/project context — none ships here.)

4. **Opt-in via `scan_modes = ["function", "module"]`** (`[tool.docpact.semantic]`)
   and/or `--scan-modes`. Default stays `["function"]` — SEM002 does not run unless
   asked.

5. **Model sensitivity is a first-class, loudly-documented constraint.** SEM002 is
   **only reliable on a `gpt-4o`-class model**; on weak models (e.g. `gpt-4o-mini`)
   it produces a 43–71% false-positive rate and must not be used. This is stated
   prominently in the README and the rule doc, not buried. Unlike SEM001 (which the
   spike validated as usable even on `gpt-4o-mini`), SEM002's task is harder for a
   given model, and we do not pretend otherwise.

6. **Reuses the existing infrastructure** — `LLMBackend` protocol + factory, the
   analyzer's batching/JSON path, `RuleResult` output, `finding_threshold`. No new
   backend and no new subsystem; SEM002 is a second prompt + a module-unit collector.

## Rationale

**The spike did its job — including when it argued against building.** The first run
would have shipped a 71%-FP rule had we trusted it; the discipline of measuring
*before* building caught that the inputs, not the task, were broken. The reversal is
the strongest possible evidence for the chosen rubric: the same modules, same
planted cases, flip from 71% to 0% FP when the prompt forbids enumeration and the
model is capable. We ship the exact rubric and prompt clause the spike validated.

**Consistency-not-completeness is the whole game.** The single clause "never flag for
omitting symbols" is the difference between a 71%-FP rule and a 0%-FP rule. It is
the module-level analogue of the issue-#11 hardening for SEM001 (read the section in
full; canonical-empty is correct). Encoding it in the shipped prompt is non-negotiable.

**Both dimensions earn their place.** My going-in hypothesis was that orientation was
a taste-driven FP magnet to be dropped. The spike refuted that: the magnet was the
prompt, not the dimension. Hardened, orientation hit 0 FP and cleanly caught the
boilerplate cases scope correctly left alone. Dropping either dimension would lose
real catches (domain-mismatch needs scope; boilerplate needs orientation) for no FP
benefit.

**Symbols suffice, so we don't pay for project context.** Building `context_files`
ingestion (read README/CLAUDE/docs, hash them for cache invalidation, budget them
into the prompt) is real cost that the spec's design assumed. The spike shows it buys
nothing for scope+orientation. Not building it keeps SEM002 cheap and its prompt small.

**Model sensitivity must be loud, not a footnote.** SEM001 set an expectation that
SEM "works" on the free `gpt-4o-mini` on-ramp. SEM002 breaks that expectation — and a
user who runs it on `gpt-4o-mini` gets a flood of false positives that would discredit
the whole tool. The honest, trust-preserving move is to say so prominently and, per
the revisit triggers, consider defaulting it off or warning when a weak model is
configured.

## Alternatives considered

### Alternative A: Don't build module-level scan

**Considered because** the first spike run showed 43–71% FP, and module docstrings are
lower-value than function/tool docstrings (agents read the latter far more).

**Not chosen because** the high FP was an artifact of model + prompt, not the task;
the hardened/`gpt-4o` run is 0 FP with full recall, stable across runs. Declining now
would repeat the original mistake of trusting a confounded measurement.

### Alternative B: A `scan_modes=module` flavour of SEM001 (same code)

**Considered because** it avoids allocating a new error code and reuses SEM001's
message plumbing.

**Not chosen because** the unit, rubric, and verdicts differ (scope/orientation vs
cargo-cult/hidden-contract/empty). Folding both under SEM001 would make one code mean
two different checks — a stable-API violation (§18.1) and a confusing suppression
target. A distinct `SEM002` is the honest shape.

### Alternative C: Require the project-`context` input variant (build `context_files`)

**Considered because** the spec designed `context_files` for module-level, on the
theory that "orientation vs siblings" needs project context.

**Not chosen because** the `symbols` variant already reached 0 FP on both dimensions;
context bought nothing measurable for what we ship. Building it would add prompt size,
token cost, and cache-invalidation complexity for no demonstrated gain. Reserved for a
future dimension that needs it.

### Alternative D: Ship one dimension only (scope-only, or orientation-only)

**Considered because** a single dimension is a smaller surface and simpler prompt.

**Not chosen because** both hit 0 FP and each catches a defect the other misses (a
contentful-but-wrong-domain docstring is scope-only; a boilerplate docstring is
orientation-only). Dropping one loses real signal for no FP reduction.

## Consequences

### Positive

- Closes the module-docstring meaning gap (DOC002 ensures presence; SEM002 judges
  usefulness), validated at 0 FP on real docstrings.
- Cheap: no `context_files`, no new backend, reuses the SEM analyzer and output.
- The "consistency-not-completeness" prompt clause is a reusable lesson for any future
  module-aware semantic rule.

### Negative

- **Model-sensitive**: unusable on weak models (43–71% FP). This narrows who can run
  it and demands loud documentation; a user who ignores the warning gets a bad first
  impression of the whole tool.
- Validated only on docpact's own (unusually good) docstrings + synthetic planted
  cases. Real-adopter-tree validation is still owed (revisit trigger 1).
- A second SEM prompt to maintain; prompt-version fragility (the deferred §21 Q1
  problem) now spans two rules.

### Neutral

- `scan_modes` config (designed-not-built) becomes real for `["function", "module"]`.
- SEM002 inherits SEM001's advisory posture and `finding_threshold`/severity controls.
- The throwaway spike (`scripts/spike_semantic_module.py`) is removed once SEM002 ships,
  as `scripts/spike_semantic.py` was after SEM001.

## Revisit triggers

1. **Real-adopter-tree validation.** Before treating SEM002 as production-grade, run it
   on a messier external codebase. If FP rises materially on real (non-docpact)
   docstrings, tighten the prompt or narrow the rubric before promoting it.
2. **Model-sensitivity guardrail.** If users run SEM002 on weak models despite the
   warning and report noise, add a guard — warn (or default module-scan off) when the
   configured model is not on an allowlist of known-capable models.
3. **A capable model becomes unavailable on a free/cheap tier.** If validating at scale
   is blocked by rate limits on capable models, revisit the backend story — first by
   pointing `openai-compat` at a provider's OpenAI-compatible endpoint (Gemini,
   Anthropic), and only then by building a native adapter.
4. **`context_files` demand.** If a future module-level dimension genuinely needs
   sibling/project context (e.g. "does this module overlap a sibling?"), build the
   reserved `context_files` plumbing then, under its own decision.

## References

1. ADR-008 — opened the SEM layer; listed module-level scan as designed-not-built
2. `scripts/spike_semantic_module.py` — the spike (gpt-4o-mini 71%/43% FP → gpt-4o 0% FP, hardened prompt, stable across two runs)
3. Spec §12.2 (semantic design, two scan modes), §15.1 (`scan_modes`, `context_files`), §18.1 (stable error codes)
4. SEM001 prompt-hardening (adopter issue #11; PROGRESS.md) — the precedent: read the section in full, consistency over pedantry

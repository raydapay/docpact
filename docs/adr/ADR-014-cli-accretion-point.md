# ADR-014: cli.py is the accretion point — extract a CheckEngine when the REG010/crossfile seam is next touched

**Status:** Accepted
**Date:** 2026-06-01
**Deciders:** Ray
**Related:** ADR-006 (interim architecture posture), ADR-012 (same-file REG010 default pass), spec §10–§11

## Context

`cli.py` is ~1600 lines and is the one module trending the wrong way. The rule
engine and model layer are clean and stable; the orchestrator is not. A peer
review flagged that `_check_one_file` now juggles seven distinct concerns in one
function: the file-level pre-pass, the function-level rule loop, registry
extraction, the same-file REG010 leg, the cross-file Tier-3 floor merge, the
FIX003 post-pass, and the `crossfile_active` double-report guard.

That last concern is the live risk. REG010 runs its same-file leg in the default
`check` *unless* `--crossfile` is active, because then the cross-file pass owns
REG010 and running both would double-report (ADR-012). That is a subtle
cross-cutting condition with no structural boundary around it — exactly where
the next orchestration bug will live.

The question is not *whether* `cli.py` should be decomposed — it should. The
question is *when* paying that cost is justified, given the refactor is large,
behavior-preserving, and its primary risk is introducing the very bugs it aims
to prevent.

## Decision

Do not extract a `CheckEngine` speculatively now. Record `cli.py` as the known
accretion point and bind the refactor to a concrete trigger: **the next change
that touches the REG010 / cross-file interaction** (the same-file vs. cross-file
ownership split, the `crossfile_active` guard, or the Tier-3 floor merge). When
that change lands, isolate that seam — extract the orchestration of a single
file's checks (pre-pass → function loop → registry/REG010 → cross-file merge →
post-pass) out of `cli.py` into a dedicated `CheckEngine`/pipeline object, so
`cli.py` returns to argument parsing and dispatch — as part of that change,
not as a standalone refactor.

## Rationale

The refactor's value is real but latent; the cost and risk are immediate. Tying
it to the next REG010/crossfile edit means we pay the decomposition cost exactly
when we are already in that code with its invariants paged in, and when a fresh
test for the triggering change can also cover the extraction. A speculative
behavior-preserving rewrite, by contrast, spends risk now against a benefit we
cannot schedule, and the reviewer themselves judged it "not urgent."

This is consistent with ADR-006's interim-architecture posture: defer structural
investment until a forcing function makes it cheap and necessary, rather than
pre-building abstractions.

## Alternatives considered

### Alternative A: Extract `CheckEngine` now

Pull the per-file orchestration into a dedicated object immediately. Rejected:
it is a large behavior-preserving change whose main failure mode is regressions
in the exact cross-cutting logic (REG010/crossfile) it targets, with no
accompanying feature change to justify or naturally test it. High risk, benefit
we cannot time.

### Alternative B: Do nothing, leave it implicit

Accept the accretion silently. Rejected: the next agent session has no memory of
this review, would not know `cli.py` is the watched module, and might add an
eighth concern to `_check_one_file` without recognizing the trend. The cost of
recording the trigger is one ADR; the cost of losing it is an avoidable regression.

### Alternative C: Add a smaller guard now (extract only the `crossfile_active` condition)

Wrap just the double-report guard in a named helper without the full engine.
Rejected as premature half-measure: it would touch the seam without the forcing
function, re-introducing the timing/risk objection on a smaller scale, and a
named helper without the surrounding pipeline boundary does little for the real
problem (the seven-concern function).

## Consequences

### Positive

- The refactor lands when it is cheapest and best-tested — inside a change that
  already touches the seam and ships its own tests.
- The accretion point is now documented; a future session inherits the intent
  instead of rediscovering it.
- No risk spent speculatively.

### Negative

- `cli.py` stays large in the interim. If no REG010/crossfile change comes for a
  long time, the decomposition is deferred indefinitely (see revisit trigger).
- The trigger is a judgment call: "touches the REG010/crossfile interaction" has
  a fuzzy boundary. The deciding agent must err toward extracting when unsure.

### Neutral

- The target shape (a `CheckEngine`/pipeline owning one file's check lifecycle)
  is sketched here but not specified in detail; the triggering change defines the
  exact interface.

## Revisit triggers

- **Primary:** any change touching the REG010 same-file/cross-file ownership
  split, the `crossfile_active` guard, or the Tier-3 floor merge — extract the
  seam as part of it.
- **Secondary:** `cli.py` crosses ~2000 lines, or `_check_one_file` gains an
  eighth distinct concern, before the primary trigger fires — at that point the
  accretion has outrun the wait, and the extraction should be scheduled on its
  own.

## References

- Peer review, 2026-06-01 (finding 1: "cli.py is the architectural pressure point").
- ADR-006: interim architecture posture.
- ADR-012: same-file REG010 default pass (origin of the `crossfile_active` guard).

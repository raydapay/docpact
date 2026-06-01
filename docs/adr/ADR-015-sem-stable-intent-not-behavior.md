# ADR-015: SEM codes guarantee stable intent, not stable behavior

**Status:** Accepted
**Date:** 2026-06-01
**Deciders:** Ray
**Related:** ADR-008 (open semantic layer), ADR-013 (module-level SEM002), spec §18.1 (stable error codes), spec §12.2 (semantic reliability)

## Context

Spec §18.1 makes error codes a stable API: once a code ships, it never changes
meaning and is never reused. This guarantee is unambiguous for the deterministic
rules (DOC*, FIX*, REG*, TY*, PARSE*): the code names a contract, the analyzer
is a pure function of the AST, and a unit test pins the output for a given input.
"Stable meaning" there means **stable behavior on stable input**.

SEM codes break that chain. SEM001 and SEM002 are an LLM prompt plus a model.
The *meaning* a reader infers ("weak module docstring: scope inconsistency or
boilerplate orientation") is stable, but the *behavior* is not: the same input
can yield different findings across model versions and prompt revisions, and no
unit test can pin it (the §12.2 reliability table is explicit about this). SEM002's
prompt has already needed one load-bearing rewrite — the consistency-not-
completeness clause that moved the false-positive rate from 71% to 0% on gpt-4o
(ADR-013). Under a naive reading of §18.1, that rewrite silently changed the
behavior of a "stable" code with nothing to catch it.

So: does §18.1's stable-meaning guarantee apply to non-deterministic rules at
all, and if the prompt is going to keep evolving, how does a finding stay
traceable to what produced it?

## Decision

**The §18.1 stable-code guarantee does not extend to behavior for SEM codes.**
By their nature SEM codes guarantee stable *intent* — what the rule is trying to
detect, and its diagnostic message vocabulary — not stable *behavior*. Behavior
tracks the **(model, prompt)** pair, and:

1. **We cannot pin the model.** "gpt-4o-class" is an external, silently-updated
   target. We state the dependence; we do not pretend to control it.
2. **We do pin the prompt.** The prompt is part of docpact's source — the
   structure-creating scaffolding is code, versioned in git like any other code,
   and a prompt change is a reviewable code change, not a silent drift.
3. **Every SEM run surfaces its provenance.** `docpact semantic` emits the model
   id and a prompt fingerprint (`builtin:<hash>`) in both text and JSON
   (`meta.semantic`) output, so any finding is traceable to the exact
   (model, prompt) that produced it. The fingerprint moves whenever we edit the
   prompt — making a "stable code, evolved behavior" event visible rather than
   silent.

**User prompt override is the designed mechanism, rubric-only, not yet built.**
We do not claim our rubric is optimal; a team can do better for its own
conventions. The designed override lets a user supply **only the rubric prose**
(the "what counts as weak" judgement) via config, while docpact retains ownership
of the **output-contract scaffolding** (the JSON shape and verdict vocabulary the
parser depends on). The override is documented here as the intended mechanism and
deferred to build alongside the other designed-not-built SEM features
(`sample-rate`, `any-llm`, `context_files`). When it ships, a custom rubric
surfaces as `custom:<hash>` in provenance.

This decision is reflected in spec §18.1 (carve-out) and the §12.2 reliability table.

## Rationale

The two framings of "meaning" had to be reconciled. For a deterministic rule the
contract pins behavior; for a SEM rule the contract only pins intent, because the
mechanism is a probabilistic judge we cannot make deterministic without making it
useless. Pretending the same guarantee holds would be dishonest and would tempt a
future maintainer to treat a prompt rewrite as invisible. Naming the weaker
guarantee explicitly, and making the behavior-determining inputs (model + prompt)
observable in output, is the honest containment: the code is stable as a *name
for a concern*, and provenance carries the *identity of the behavior*.

Pinning the prompt but not the model is not a half-measure — it reflects what we
actually control. The prompt is ours; surfacing only a prompt version without the
model would manufacture false pinnability, which is why provenance carries both
or neither.

Rubric-only (not whole-prompt) override is the load-bearing safety choice — see
the alternative below.

## Alternatives considered

### Alternative A: Treat SEM codes under the full §18.1 guarantee

Hold SEM001/SEM002 to "stable behavior on stable input" like the deterministic
rules. Rejected as impossible to honor: the behavior depends on an external model
and a probabilistic judge; there is no test that can pin it, and the prompt has
already had to change to fix a 71% FP rate. The guarantee would be fiction.

### Alternative B: Version the prompt only (no model id in output)

Surface a `prompt_version`/fingerprint but not the model. Rejected: the model is
the larger unpinned variable. A prompt fingerprint without the model id implies
the output is reproducible from the prompt alone, which is false. Provenance must
carry both to be honest, so they are surfaced together.

### Alternative C: Whole-prompt override (user replaces the entire system prompt)

Simplest to ship and maximally "it's your prompt now." Rejected as a silent
footgun: the prompt and the parser are coupled (the system prompt ends with the
exact JSON shape and `good/weak` vocabulary `_extract_json` expects). docpact does
**no prompt sanitizing** — a user who carves their own prose can drop or mangle
the output-contract instruction, and because the analyzers skip-don't-crash on
unparseable replies, the result is **silently zero findings** that read as "clean,"
not "broken." For an advisory tool that is the worst failure mode: it lies by
omission across the user's whole pipeline. Rubric-only override confines the user
to the judgement prose and keeps the output contract wired inside docpact's
globally-enforced structure, so an override cannot silently kill the pipeline.
This footgun and the no-sanitizing posture are documented loudly wherever the
override is described.

## Consequences

### Positive

- Honest contract: readers and maintainers know a SEM prompt rewrite changes
  behavior, and provenance makes each such event visible.
- A finding is traceable to its exact (model, prompt) — useful when triaging a
  surprising advisory result or comparing runs across model versions.
- The deferred rubric-only override has a safe design on record before any code
  exists, so it can't be built the unsafe (whole-prompt) way later by default.
- Deterministic rules' §18.1 guarantee is untouched and, by contrast, sharpened.

### Negative

- SEM codes carry a weaker promise than their DOC*/REG* siblings under the same
  code-namespace convention; the distinction must be taught (docs carry it).
- Provenance adds an additive `meta` key to `semantic` JSON output (backward
  compatible; `check` output is byte-identical).
- The override remains designed-not-built — users wanting to tune the rubric must
  wait, and the designed shape is a forward commitment.

### Neutral

- The prompt stays a single fused string for now (rubric + output-contract
  footer). The rubric/footer split is only required when the override is built;
  the fingerprint currently covers the whole system prompt.

## Revisit triggers

- A user actually needs rubric override → build it (rubric/footer split,
  `custom:<hash>` provenance, the no-sanitizing warning surfaced at the config site).
- A SEM rule becomes deterministic enough to pin (e.g. a local pinned model with a
  fixed seed) → reconsider whether its behavior guarantee can strengthen.
- The §18.1 carve-out wording proves ambiguous for a third SEM code → revisit the
  spec language.

## References

- ADR-008: open semantic layer.
- ADR-013: module-level SEM002 (origin of the 71%→0% prompt rewrite).
- Peer review, 2026-06-01 (finding 2: stable code vs. untestable behavior).
- spec §18.1 (stable error codes), §12.2 (semantic reliability table).

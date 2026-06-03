# ADR-017: Reflective class-based agent-tool detection via tier assignment

**Status:** Accepted — deferred (unscheduled)
**Date:** 2026-06-03
**Deciders:** Ray
**Related:** ADR-003 (tier assignment), ADR-005 / ADR-011 (registry extraction — the
contrast), ADR-009 (cross-file via LSP), ADR-016 (Sphinx + custom sections), spec §7.4,
§10, §15

**Implementation status:** Not built. No spec cycle and no release is scheduled. The
design is recorded chiefly to capture *one architectural correction* — that this is a
tier-assignment problem, not a registry problem — so a future session does not rebuild
it the wrong way. When built, it gets a phase in PROGRESS.md and this status updates.
See PROGRESS.md "Someday — designed, not built."

## Context

A feature request asked docpact to detect agent-facing tools defined reflectively:
a class derived from a framework base (`class FindSymbolTool(Tool): def apply(self, ...)`),
where the tool name is derived from the class name and the runtime MCP contract lives in
the `apply` method's docstring + signature. Serena is the motivating example.

The request modeled this on docpact's registry subsystem (ADR-005/011, `parser/registry.py`)
— proposing `name_from`, `description_from`, schema correlation. The non-trivial question
this ADR settles: **is that the right frame, and how much of the requested behavior is
genuinely new?**

## Decision

The registry frame is **rejected**; the correct frame is **tier assignment**.

When built, docpact adds a config-driven tier-assignment hook (spec §7.4, §10) that
matches a method by **(path glob, class-base token *or* class-name suffix, method name)**
and assigns a configured tier. The match is **purely syntactic, same-file, offline, and
deterministic** — consistent with ADR-003 (tier is a pure function of `FunctionInfo`,
overridable but visible in config). Minimal config shape:

```toml
[[tool.docpact.agent_tool_patterns]]
path   = "src/serena/tools/**/*.py"   # glob, anchored to project root
base   = "Tool"                       # literal base-name token in the bases list (optional)
method = "apply"
tier   = 3
```

Once the `apply` method is assigned its tier, **the existing function-level rules do all
the contract enforcement with no new rule code**: DOC007 (every param documented / no
phantom param), DOC012 (required sections per tier), DOC013/DOC052 (non-empty section
bodies), DOC022, etc. — they already operate on any function or method.

Explicitly **out of scope** even when built:
- `name_from` / `description_from` — registry-correlation concepts. In the reflective
  model there is no literal registry artifact to correlate against; the method signature
  *is* the parameter source and the method docstring *is* the description. Nothing to
  cross-check, so these keys are not added.
- Class-docstring enforcement (checking the class docstring separately from the method).
  docpact rules are `(FunctionInfo, ParsedDocstring | None, RuleConfig)`; there is no
  class-level docstring rule today (DOC002 is module-level, DOC003 only checks presence).
  The runtime MCP contract comes from the `apply` method — that is what v1 enforces.
- Transitive / imported / aliased inheritance resolution (knowing `Tool` resolves to
  `serena.tools.Tool` across files). That is cross-file work (ADR-009 LSP territory),
  not the offline default. The syntactic match is the deliberate ceiling.

Not scheduled. Revisable in place until built.

## Rationale

Reframing as tier assignment collapses most of the request to existing behavior. Mapping
the requested checks to what already exists:

| Requested check | Already provided by |
|---|---|
| every param documented / no phantom param | DOC007 (on the method) |
| return documented / param docs non-empty | DOC012 / DOC013 / DOC052 |
| constraints for destructive / stability documented | DOC012 at Tier 3 |
| convertible to an MCP description | DOC050 / DOC052 |

So the genuinely new surface is **one thing**: a tier-assignment matcher keyed on
(class base/suffix, method, path). That is a sibling of the existing `per-file-tier`
glob and the `# docpact: tier=N` pragma — both already tier-assignment overrides — so it
fits the established mechanism rather than introducing a new subsystem.

The registry frame fails because Serena has **no literal module-level registry** to
extract: registration is runtime subclass discovery, and the schema is generated at
runtime from the signature + docstring. `parser/registry.py` exists to detect *divergence
between a literal schema artifact and a function*. With no artifact, there is nothing to
diverge — the "phantom/missing param" check the request wanted is just DOC007 on the
method.

Why syntactic-only matching, not real inheritance: resolving `class X(Tool)` to a
specific base across imports requires the cross-file LSP path (ADR-009), which is opt-in
and heavier. A literal base-name token match (`Tool` appears in the bases list) plus a
path glob is offline, deterministic, and good enough — with documented, bounded failure
modes (below). This keeps the default `check` offline, per the invariant ADR-009 was
careful to preserve.

## The Serena coupling (recorded honestly)

The request's stated goal was "so docpact can validate Serena." That goal is **not**
pursued: Serena's `apply` docstrings carry no Constraints/MCP sections, so detecting them
*and* flooring them to Tier 3 would make every Serena tool fail DOC012 — noise, not
signal. The irony worth recording: the reason Serena is uncheckable today is exactly the
gap ADR-016 (Sphinx custom sections) closes. If ADR-016 *and* this ADR both shipped,
Serena would become genuinely checkable at Tier 3. Until then, docpact does not target
Serena, and this ADR's justification is **architectural** (capture the registry-vs-tier
correction and the offline-syntactic-match decision), not "lint Serena."

## Alternatives considered

### Alternative A: model it as registry extraction (the request's framing)
Extend `parser/registry.py` to recognize class-based tools, with `name_from` /
`description_from`. Rejected: there is no literal registry artifact in the reflective
model, so registry correlation has nothing to correlate. The contract is the method
itself — a tier/function-rule concern, not a registry concern.

### Alternative B: full inheritance resolution via LSP
Resolve `class X(Tool)` to its true base across files (ADR-009 cross-file). Rejected for
v1: it pulls a same-file, offline capability onto the opt-in LSP path, much larger build,
slower, and unnecessary for the syntactic precision the use case needs. Reserved as a
later precision upgrade if syntactic matching proves too coarse on a real tree.

### Alternative C: class-name-suffix only (drop base-token matching)
Match purely on `class_name_suffix = "Tool"` + method. Kept as a *supported option*, not
the only mechanism — suffix conventions are real but not universal; the literal-base
token is more precise when the framework base is named consistently. Both are offered.

## Consequences

### Positive
- Reuses tier assignment + every existing function-level rule; ~one matcher of new code.
- Stays offline and deterministic (ADR-003 / ADR-009 invariants intact).
- Corrects the architectural frame before anyone builds the wrong (registry) thing.

### Negative
- Syntactic base matching has bounded, documented failure modes: **false negative** on
  aliased imports (`from serena.tools import Tool as T` → bases list shows `T`, not
  `Tool`); **false positive** on an unrelated class whose base happens to be named
  `Tool`. The path glob narrows both. These must be stated in the rule/config docs when
  built, not discovered by an adopter.
- Tier-3 flooring of detected tools is only useful alongside ADR-016 for Sphinx-style
  tools (the coupling above) — otherwise the required Constraints/MCP sections may be
  inexpressible. A scheduler must pair them or cap the floor below Tier 3.

### Neutral
- New config table `[[tool.docpact.agent_tool_patterns]]`; additive, no change to
  existing keys. Glob anchoring follows the existing `per-file-tier` root convention.

## Revisit triggers
- A real adopter runs a reflective class-based tool framework through docpact and wants
  its `apply` methods enforced → schedule; pair with ADR-016 if the docstrings are reST.
- Syntactic base matching proves too coarse on a real tree (false pos/neg rate
  unacceptable) → reconsider Alternative B (LSP inheritance resolution).

## References
- Feature request (Serena / Sphinx + class-based tool detection), 2026-06-03.
- ADR-005, ADR-011 (`parser/registry.py` — the registry model this is *not*).
- DOC007, DOC012 (`docs/rules/`).

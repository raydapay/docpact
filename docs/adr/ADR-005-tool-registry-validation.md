# ADR-005: Same-file tool-registry validation; cross-file registration out of scope

**Status:** Accepted
**Date:** 2026-05-30
**Deciders:** Ray
**Related:** ADR-003 (Tier assignment — this ADR amends it); spec §10.1 (Tier rules), §8 (No imports invariant); PROGRESS.md "MCP-REG cluster — postponed" (this ADR partially resolves it)

## Context

Some projects expose functions to an LLM not through a `@mcp.tool` decorator but
through a data structure: a module-level `list[ToolDefinition]` (or a list of raw
`{"name": ..., "description": ..., "parameters": {...}}` dicts) where each entry
names a function and carries the JSON Schema the model reads to decide how to call
it. This is the shape used by FastMCP's `add_tool`, OpenAI function calling, and
AWS Bedrock tool definitions — the de-facto standard for programmatic tool metadata.

The `parameters` JSON Schema is exactly as load-bearing as the function docstring:
the model reads it to choose arguments. But docpact has no visibility into it, so
two things can silently diverge from the function:

1. A `parameters.properties` key can name a parameter the function signature no
   longer has (a rename missed in the schema). DOC007 catches this drift in the
   docstring `Args:` section; nothing catches it in the schema.
2. The registry `description` can diverge from the docstring summary.

This was previously raised as the "MCP-REG cluster" and **postponed** (PROGRESS.md),
on the stated grounds that it "requires resolving the type of `ToolSpec(...)` across
files ... docpact operates on one file at a time; it never imports code and has no
module graph," with the architectural question — *should docpact ever cross the
per-file boundary?* — left explicitly open.

That postponement conflated two independent axes:

- **Schema dialect** — `ToolDefinition(...)` constructor vs. raw dict vs. another
  framework's shape. This is a question of *which AST node the extractor matches*.
  It carries no architectural weight.
- **Locality** — is the function defined in the *same file* as its registry entry,
  or imported into a central registration module from elsewhere?

All of the "cross-file type resolution" cost lives on the **locality** axis. The
postponement reasoning was written with a centralized-registration pattern in mind
(functions imported into a registry module), where correlating an entry to its
function genuinely needs the module graph. It does not apply to the **co-located**
pattern, where the function and its registry entry are in the same file and
correlation is a string-literal match against a `def` in the same AST.

The question this ADR answers: **should docpact validate co-located tool registries,
and if so, what exactly does it check, at what tier, and where is the boundary?**

## Decision

docpact will detect tool-registry entries **within a single file** and cross-check
them against the functions defined in that same file. Specifically:

1. **New `REG` namespace.** Provider-agnostic tool-registration validation. Not
   under `MCP`, because the pattern is not MCP-specific (`MCP001` means something
   narrower — decorator/docstring description conflict).

2. **Extraction layer.** A single-file AST pass recognizes registry entries in two
   shapes, both configurable and both **statically-evaluable only**:
   - constructor calls to a configured class, e.g. `ToolDefinition(name=..., ...)`;
   - raw dict literals, e.g. `{"name": ..., "description": ..., "parameters": {...}}`.
   Entries whose `name`/`description`/`parameters` are not literal (e.g.
   `parameters=make_schema(fn)`) are skipped — the same literals-only discipline
   DOC021 uses for default-value comparison.

3. **REG001 — phantom parameter in the registry schema** (ERROR, fires at **all
   tiers**, not fixable). Fires when a `parameters.properties` key names a parameter
   absent from the matched function's signature. This is DOC007's phantom sub-case
   lifted from the docstring `Args:` section to the JSON Schema. It is a *consistency*
   check, not a *completeness* check, so — like DOC007's phantom sub-case, DOC014,
   DOC021, DOC022 — it is not tier-gated; its applicability is gated by "does this
   function have a matching same-file registry entry," not by tier.

4. **REG002 — registry entry unmatched to a same-file function** (INFO,
   **off by default** in `select`). When an entry's `name` matches no `def` in the
   file, the entry is treated as out of scope (likely cross-file registration) and
   **silently skipped by default**. A team that wants coverage visibility opts in
   with `--extend-select REG002`; the note is `# nodo:`-suppressible like any rule.
   This realizes "silent by default, surfaced on demand" without inventing a
   verbosity mode — docpact has no verbosity concept and gains none; "verbose" here
   means "the user selected the informational rule."

5. **Registry membership drives tier assignment as a Tier 3 floor** (amends ADR-003).
   A function named by a same-file registry entry is held to **at least** Tier 3.
   A registry entry is the *programmatic equivalent* of `@mcp.tool` — the identical
   semantic signal ("this function is an agent-facing tool"), expressed as data
   rather than a decorator. Precedence (see Rationale and the spec §10.1 update):
   - The floor is `max(3, t)` where `t` is the tier the existing rules would assign.
     So an explicit `per-file-tier = 1` on the file **does not** lower a registered
     tool below Tier 3 (the floor overrides the downgrade); a `per-file-tier = 4`
     **does** raise it to 4 (the floor is a minimum, not a fixed value).
   - **Floor, not absolute** — this differs deliberately from the `@mcp.tool` rule,
     which returns Tier 3 unconditionally and ignores `per-file-tier` entirely. The
     floor is more flexible: a registered tool that is also a Tier 4 FastAPI route
     can still reach Tier 4. The decorator rule is left unchanged (not in scope).
   - **Silenceable per function via pragma.** `# docpact: tier=N` (requires
     `allow_pragma = true`) overrides the floor, including lowering below 3. This
     falls out of the existing architecture for free: the pragma is applied *after*
     `assign_tier` in `_run_checks`, so it already overrides any assigned tier.
   - **Disable-able per file and per registry config** — see item 5a.

5a. **Two config escape hatches for the tier floor** (the pragma above is the third,
   per-function, hatch):
   - **Per registry / project-wide:** `[tool.docpact.registry] assign_tier = false`
     (default `true`). When false, registries are still detected and REG001 still
     runs, but membership applies no tier floor anywhere.
   - **Per file:** `[tool.docpact.registry] no_tier_floor = ["glob", ...]`. Files
     matching a glob are detected and REG001-checked, but membership applies no tier
     floor for functions in those files. Globs are anchored to the project root, the
     same convention as `per-file-tier`.

6. **Cross-file registration remains out of scope.** Correlating an entry to a
   function in another module needs the module graph docpact deliberately does not
   build. REG002 (above) is exactly how this boundary surfaces: an unmatched entry
   is not chased to another file.

7. **Semantic / heuristic checks are out of scope** — explicitly, not merely
   deferred-with-a-reserved-code-then-shipped. Registry `description` ↔ docstring
   summary divergence (REG050, reserved) requires judging whether two free-text
   strings "mean the same thing." Any similarity heuristic (Jaccard, leading-word,
   edit distance) reproduces the DOC051 false-positive failure mode on legitimate
   condensation and synonymy. Per-parameter `properties[*].description` free-text is
   likewise unenforceable structurally. docpact enforces **structure, not meaning**;
   these belong to the author. They ship only if a precise, non-heuristic detector
   exists — none does.

Configuration (`[tool.docpact.registry]`):

```toml
[tool.docpact.registry]
tool_definition_class = ["ToolDefinition"]  # constructor shape(s); dict literals always recognized
name_field = "name"
description_field = "description"
parameters_field = "parameters"
assign_tier = true                          # registry membership → Tier 3 floor (project-wide)
no_tier_floor = ["legacy/*.py"]             # globs: detect + REG001, but no tier floor
```

Reserved codes (stable API, not shipped in v1): **REG003** — signature parameter
absent from the registry schema (the reverse, "missing" direction; deferred because
deliberate non-exposure of a parameter is legitimate and would produce false
positives). **REG050** — registry description ↔ docstring summary divergence
(out of scope per item 7).

## Rationale

**The per-file boundary is preserved, not crossed.** This is the load-bearing point.
The earlier postponement feared building a partial type checker. The co-located
check requires none of that: the extractor reads literals from one AST and matches
a `name` string against a `def` in the same AST. It is strictly less cross-cutting
than the existing `__all__` tier rule, which already reads a module-level data
structure to classify functions in the same file. The "no imports, one file at a
time" invariant (spec §8) is untouched.

**Dialect support is cheap; locality is the only hard axis.** Supporting both
constructor calls and raw dict literals is two AST node shapes in one extractor.
This is why "OpenAI-style schemas" and "the `ToolDefinition` pattern" are the same
feature, not two — they differ only in the node the extractor matches, and both are
co-located.

**REG001 is high-confidence; the description check is not.** A `properties` key
either names a real parameter or it does not — there is no judgment call, no
heuristic, no false-positive class. This is the half of the original request that is
structurally checkable, and it catches the concrete drift the requesting team
described (a `amount` → `amount_cents` rename left stale in the schema). The
description-similarity half is the half that is not structurally checkable, and
shipping a heuristic for it would repeat the DOC051 mistake.

**Registry membership should drive tier — the consistency argument.** docpact
already forces Tier 3 on `@mcp.tool` (`tiers.py:76`). A `ToolDefinition` registry
entry carries the *same* information: this function is agent-facing. Treating the
decorator as a Tier-3 signal but ignoring the equivalent data structure is an
arbitrary asymmetry — the same function, exposed the same way to the same audience,
would be held to a different documentation standard purely based on *how* it was
registered. Setting a Tier 3 floor from registry membership removes that asymmetry
and, as a side benefit, lets registry-using projects delete the `per-file-tier = 3`
workaround they currently maintain by hand (which is coarser — it bumps every
function in the file, not just the registered ones). The floor is overridable per
function (pragma), per file (`no_tier_floor`), and per project (`assign_tier =
false`), so the bump is never a trap.

**The alternative — not driving tier — is the less consistent option, and we
reject it deliberately.** One could detect the registry for REG001's cross-check but
leave tier assignment alone, requiring `per-file-tier` to raise the tier. This keeps
tier assignment's input set unchanged and avoids amending ADR-003. We reject it
because it preserves exactly the asymmetry above: docpact would *know* a function is
a registered tool (it read the entry to run REG001) yet decline to treat it as one
for tier purposes. That is harder to explain than the symmetric rule and leaves the
hand-maintained workaround in place. The cost of the chosen option — registry
membership becomes a tier input, so reproducing a tier by hand means also reading
the registry — is acceptable: the registry is in the same file, as visible as the
decorator it mirrors.

## Alternatives considered

### Alternative A: Keep the whole cluster postponed (status quo)

**Considered because.** The original postponement is on record; not reopening it is
the lowest-effort path and avoids a new subsystem.

**Not chosen because.** The postponement rested on a cross-file-resolution cost that
does not exist for the co-located pattern. Leaving it postponed declines a
high-confidence, low-architectural-cost check on a false premise.

### Alternative B: Extend DOC007 instead of a new namespace

**Considered because.** The phantom-param logic is architecturally similar to
DOC007's existing signature ↔ `Args:` check; reusing the code would avoid a new
namespace.

**Not chosen because.** Every current rule has the signature
`(FunctionInfo, ParsedDocstring | None, RuleConfig) -> list[RuleResult]`. The
registry check needs a *third* input — the matched registry entry — which no rule
receives today. Folding it into DOC007 would either overload that rule's contract or
smuggle registry data through `RuleConfig.options`. A separate namespace with its
own extraction layer is the honest shape, and it keeps DOC007's meaning stable
(stable error codes, spec §18.1).

### Alternative C: Put the rules under the `MCP` namespace

**Considered because.** These rules concern tool exposure, and `MCP001` already
lives there.

**Not chosen because.** The pattern is provider-agnostic (OpenAI, Bedrock, FastMCP,
plain dicts) and not tied to the Model Context Protocol. `MCP001` is specifically
the decorator/docstring conflict. A `REG` namespace names the actual concept —
programmatic registration — and leaves room for registration checks that have
nothing to do with MCP.

### Alternative D: Detect the registry for REG001 but do not change tier

**Considered because.** It avoids amending ADR-003 and keeps tier assignment's input
set unchanged; `per-file-tier` remains the way to raise tier.

**Not chosen because.** It is the less consistent option (see Rationale): docpact
would read the registry entry to run REG001 yet refuse to treat the function as the
tool it demonstrably is for tier purposes. Documented here, per the decision to
record the logic *and* the rejected alternative.

### Alternative E: Ship the description-similarity check with a heuristic

**Considered because.** It is half of what the requesting team described, and a
similarity threshold (Jaccard < 0.5, leading-word match) is implementable.

**Not chosen because.** It is the DOC051 failure mode exactly: legitimate
condensation, synonymy, and stylistic variation between a summary and a condensed
description trip any threshold. docpact enforces structure, not meaning. The check
ships only behind a precise, non-heuristic detector, which does not exist. Code
REG050 is reserved so it can ship under that code if one emerges.

## Consequences

### Positive

- Closes the structurally-checkable drift between a function signature and its
  programmatic tool schema — the high-confidence half of the request — with no
  false-positive class.
- Generalizes across registration dialects (constructor and dict) and frameworks
  (FastMCP, OpenAI, Bedrock) at near-zero marginal cost over a single dialect.
- Registry-using projects can delete hand-maintained `per-file-tier = 3` overrides;
  tier becomes precise (registered functions only).
- Resolves the long-open "should docpact cross the per-file boundary" question for
  this case: **no** — the feature is explicitly co-located, and the boundary is made
  visible via opt-in REG002 rather than hidden.

### Negative

- A new extraction layer and a new rule namespace — more surface to maintain than a
  rule addition.
- Registry membership becomes a tier-assignment input (amends ADR-003), so
  reproducing a function's tier by hand now means also reading the module's
  registry, not just the function's decorators and name.
- Cross-file registration — a real and common pattern — remains uncovered. REG002
  surfaces the gap when opted into, but does not close it.
- The description-divergence drift the team also raised is *not* addressed; this is
  by design, and the docs must say so plainly to avoid an expectation gap.

### Neutral

- The `[tool.docpact.registry]` config shape is fixed by this ADR and propagates
  forward.
- REG002 defaults off, so the feature is silent for projects whose registries are
  fully cross-file — they get nothing unless they opt in, which is the intended
  behavior.

## Revisit triggers

1. **Demand for the reverse direction (REG003).** If users report missing-parameter
   drift (a signature parameter the schema omits) often enough that the
   deliberate-non-exposure false-positive concern is outweighed, ship REG003.
2. **A non-heuristic description-equivalence detector becomes available.** If a
   structured-comparison or otherwise precise method emerges, ship REG050 under the
   reserved code (cf. DOC051's reserved status).
3. **Cross-file registration demand with a concrete resolution model.** If multiple
   teams need the imported-function pattern and a module-graph layer is justified,
   that is a separate ADR — it crosses the per-file boundary this ADR preserves.
4. **A registration dialect appears that is neither a constructor call nor a dict
   literal** (e.g. a builder API, `add_tool(fn, schema=...)`). Extend the extractor
   and document; if the shape needs config beyond class/field names, revisit the
   `[tool.docpact.registry]` schema.

## References

1. ADR-003 — Tier assignment by context (amended by item 5 of this decision)
2. Spec §10.1 — tier assignment rules; §8 — no-imports invariant
3. PROGRESS.md — "MCP-REG cluster — postponed" and "Deferred with reasoning" (DOC051)
4. Originating request — Aluma PDR project, `ToolDefinition` registry detection

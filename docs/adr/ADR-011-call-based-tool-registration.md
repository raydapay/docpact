# ADR-011: Call-based tool registration — builder-call extraction, indirect descriptions, handler-keyed tier floor

**Status:** Accepted
**Date:** 2026-05-31
**Deciders:** Ray
**Related:** amends ADR-005 (items 2 and 5 — the recognized extraction shapes and the Tier 3 floor); realizes ADR-005 revisit trigger #4 (a registration dialect that is neither a constructor call nor a dict literal); spec §15.1 (registry config), §10.1 (tier floor); ADR-009/ADR-012 (the cross-file / same-file REG010 legs this enables for the same adopter); originating adopter feedback (a hand-rolled MCP tool surface, `register_tool(ToolSpec(...))`)

## Context

ADR-005 recognizes tool-registry entries in exactly two shapes, and only when they
appear as **elements of a module-level list literal** (`X = [ToolDefinition(...), ...]`
or `X = [{"name": ...}, ...]`). The extractor walks `tree.body`, takes assignments
whose value is an `ast.List`, and inspects the list elements (`parser/registry.py:115-122`).

An adopter exposes its agent-facing tools through a different, equally common idiom:
a frozen `ToolSpec` dataclass passed to a registration **call** at import time —

```python
register_tool(ToolSpec(
    name="describe_provider",
    description=_DESCRIBE_PROVIDER_DOCSTRING,   # a module-level string constant
    input_model=DescribeProviderInput,           # a same-file Pydantic class
    service_function=describe_provider_tool,      # the handler (name ≠ tool name)
))
```

This is a module-level **expression statement** (`ast.Expr` → `ast.Call`), not an
assignment and not a list. `_assignment_value` returns `None`, the statement is
skipped, and **no entry is extracted at all**. The adopter's run confirms it: the
cross-file pass reported "0.0 ms — no cross-file entries to resolve." Their own
diagnosis (an import-locality limitation in REG010) is downstream of this: nothing
reached REG010 because nothing was extracted.

ADR-005 revisit trigger #4 anticipated exactly this: *"A registration dialect appears
that is neither a constructor call nor a dict literal (e.g. a builder API,
`add_tool(fn, schema=...)`). Extend the extractor and document; if the shape needs
config beyond class/field names, revisit the registry schema."* This ADR is that
extension.

The adopter's pattern surfaces three coupled sub-questions, all on ADR-005's
**dialect axis** (no module graph, no cross-file resolution — that axis is ADR-009's):

1. **What call positions does the extractor recognize** beyond list-literal elements?
2. **A Name-bound description.** `description=_DESCRIBE_PROVIDER_DOCSTRING` is a
   module-level string constant, not a string literal in the call. Today the literals
   discipline yields `description_arg_keys = None` (no parse), so REG010 can never
   fire even once the entry is extracted. Should a same-file `NAME = "..."` binding
   be resolved?
3. **Tool name ≠ handler name.** The Tier 3 floor (ADR-005 item 5) keys on the
   entry's `name`, which for the decorator-equivalent convention equals the `def`
   name. Here `name="describe_provider"` is the external tool name and the function
   is `describe_provider_tool` (the `service_function`/handler). The floor would
   match no `def`. How does the floor land on the right function — and only it,
   not the whole file?

The question this ADR answers: **how does docpact recognize call-based registration,
resolve an indirect description, and floor the correct handler — without crossing the
per-file boundary or relaxing determinism?**

## Decision

All three legs stay same-file, static, and deterministic. No new architectural
surface; the existing `[tool.docpact.registry]` field-map (`name_field`,
`description_field`, `input_model_field`, `handler_field`, …) is reused as-is.

1. **Broaden extraction to recognize a configured-class constructor (a name in
   `tool_definition_class`) at module level in four bounded positions:**
   - (a) a bare expression statement that *is* the constructor — `ToolSpec(...)`;
   - (b) an assignment value — `X = ToolSpec(...)`;
   - (c) an element of a module-level list literal — `X = [ToolSpec(...), ...]`
     (the existing behavior, preserved);
   - (d) a **direct argument** to a module-level call — `register_tool(ToolSpec(...))`.

   Recursion is bounded to exactly these positions. docpact does **not** descend into
   nested calls beyond one level, comprehensions, conditionals, loops, dict/set
   values, or function bodies — those reintroduce the non-determinism and
   over-matching the module-level discipline exists to prevent. The literals-only
   discipline on entry fields (ADR-005 item 2) is unchanged: a non-literal `name`
   still skips the entry; a non-literal `parameters` still yields `property_keys =
   None`. Raw dict literals continue to be recognized only as list elements (position
   c), as today — a bare `{...}` statement is not a registration idiom.

   No new config key. Matching the already-declared `tool_definition_class` name
   wherever it appears in these positions is sufficient; `registration_call` (naming
   the wrapper, e.g. `["register_tool"]`) is **reserved**, to be added only if a real
   over-matching report makes the extra precision worth the config surface.

2. **Resolve an indirect, same-file description through one hop.** When the
   description field's value is a bare `ast.Name`, docpact resolves it against a
   table of **module-level `NAME = <string>` bindings** built from the same AST. A
   single hop to a string literal (including implicitly-concatenated adjacent string
   literals, which are still literals) is resolved and fed to the existing
   description-parsing path (`description_arg_keys`, `description_text`,
   `has_description`). Anything that is not a single Name→string-literal binding —
   an f-string, a `.format(...)`/concatenation involving a call, a name bound to a
   non-literal, a name bound more than once, or an imported name — is **not** resolved
   and the fields stay `None`/absent exactly as today. This is same-file constant
   folding, not expression evaluation.

3. **Floor the registered handler, scoped to it.** The Tier 3 floor's name set
   (`_registry_floor_names`) gains, in addition to each entry's `name`, the
   `handler_ref` name of every entry **whose handler is defined in the same file**.
   The floor then lands on `describe_provider_tool` (the actual agent-facing function)
   at `max(3, t)`, and on nothing else — private helpers like `_retag_iso` in the
   same module keep their assigned tier. The existing `name`-keyed behavior is
   retained for the convention where the entry `name` *is* the `def` name. All three
   ADR-005 escape hatches (per-function pragma, `no_tier_floor` glob, project-wide
   `assign_tier = false`) apply unchanged.

## Rationale

**The per-file boundary is preserved — this is still the same-file feature ADR-005
defined.** Every leg reads literals and bindings from one AST: a constructor in a new
syntactic position, a `NAME = "..."` binding in the same module, a `def` in the same
module. No import is followed; the spec §8 no-imports invariant is untouched. This is
strictly less cross-cutting than the existing `__all__` tier rule.

**Recognizing the call shape is the dialect axis ADR-005 already committed to
extending.** ADR-005 separated *dialect* (which AST node the extractor matches —
"no architectural weight") from *locality* (cross-file — the hard axis). Call-wrapped
registration is purely a dialect: `register_tool(ToolSpec(...))` is the same
agent-facing signal as `@mcp.tool` and as a list of `ToolDefinition`, expressed
through a builder call. Holding it to a different standard purely because of *how* it
is registered is the arbitrary asymmetry ADR-005's Rationale already rejected.

**Class-name-anywhere has higher recall than a wrapper-name key, at lower config
cost.** Positions (b) and (d) together cover both the inline form
(`register_tool(ToolSpec(...))`, via d) and the two-step form
(`spec = ToolSpec(...); register_tool(spec)`, caught at the construction site via b,
regardless of how it is later registered). A `registration_call` key would catch only
the inline form unless it *also* added (b), at which point the extra key buys nothing.
The feared cost — a `ToolSpec(...)` constructed but never registered being treated as
an entry — is benign: it is still guarded by the literal-`name` requirement, and an
unmatched entry hits REG002, which is off by default. Constructing a
`ToolSpec(name=..., input_model=...)` *is* declaring a tool contract; checking its
parity is not wrong even if `register_tool` lives elsewhere.

**The indirect description is same-file constant folding, bounded by a bright line.**
The literals-only discipline (ADR-005 item 2, DOC021) exists to avoid an open-ended
evaluator that would chase arbitrary expressions and lose determinism. A single
module-level `NAME = <string literal>` binding is none of that — it is the same kind
of static, in-file fact as a list element, resolved by one table lookup, fully
deterministic. The bright line is explicit and narrow: one hop, literal target,
single binding, same file. Everything else stays unresolved, so no new false-positive
class is introduced. The contract a coding agent actually reads is frequently a
reused constant kept out of the handler docstring on purpose; tying contract rules
exclusively to inline string literals misses that whole class of real surfaces.

**The floor must key on the handler, because in this idiom the handler is the
function.** ADR-005's `name`-keyed floor assumed the decorator-equivalent convention
(`entry.name == def name`). The builder idiom separates the external tool name from
the handler symbol, so `name`-keying floors a phantom. Keying additionally on a
same-file `handler_ref` lands the floor on the real agent-facing function and nothing
else — which is also what lets the adopter delete the blunt `per-file-tier = 3`
workaround that floored every helper in the module (the noise they reported). This is
the precise-tier benefit ADR-005 promised, extended to the idiom where tool name and
handler name diverge.

## Alternatives considered

### Alternative A: add a `registration_call` config key

Name the wrapper function(s) explicitly (`registration_call = ["register_tool"]`) and
inspect their arguments for a configured constructor.

**Considered because** it is more precise — it only treats a constructor as an entry
when it is an argument to a declared registration call, eliminating the
"constructed-but-not-registered" match entirely.

**Not chosen because** the precision buys little: the over-match it prevents is benign
(literal-`name` guard + REG002-off), and it has *lower* recall — it misses the
two-step `spec = ToolSpec(...); register_tool(spec)` form unless paired with
position (b), which on its own already covers both forms. It also adds config surface
to a feature whose adopters' loudest complaint is configuration friction. Reserved,
not deleted: if a real project reports over-matching from class-name-anywhere, this is
the precision knob to add.

### Alternative B: keep list-literal-only extraction (status quo)

**Considered because** it is the lowest-effort path and avoids touching the extractor.

**Not chosen because** it declines ADR-005 revisit trigger #4 on a false premise — the
builder call is a dialect, not a cross-file problem, and the trigger explicitly
scoped "extend the extractor" for exactly this. The call-wrapped form is at least as
common as the list-literal form (Pydantic-AI, hand-rolled FastMCP wrappers, any
"spec object → `register()`" surface), so leaving it unextracted makes the entire
REG/MCP value proposition a no-op for that whole family.

### Alternative C: resolve descriptions through arbitrary expressions

Follow `.format(...)`, concatenation, f-strings, or multi-hop bindings to assemble the
description text.

**Not chosen because** it is the DOC051 / non-determinism failure mode: chasing
arbitrary expressions makes the result depend on evaluation docpact must not perform,
and produces a false-positive class on dynamically-assembled text. The bright line —
one hop, single binding, literal target, same file — is the largest extension that
stays purely static and deterministic.

### Alternative D: floor the whole file (rely on `per-file-tier = 3`)

**Considered because** it needs no change — registry-using projects can already set
`per-file-tier = 3` on their tool modules.

**Not chosen because** it is precisely the noise the adopter reported: flooring every
function in the module bumps private helpers (`_retag_iso`) to Tier 3 and buries the
real findings under spurious "missing Raises/Constraints" diagnostics on internal
code. ADR-005 already identified per-file flooring as the coarse workaround the floor
exists to replace; this ADR extends that precision to the separated-handler idiom.

### Alternative E: also correlate REG001 / REG002 via `handler_ref`

Match the phantom-parameter and unmatched-entry checks against the handler symbol, not
just the entry `name`.

**Not chosen — out of scope here, and unnecessary for this adopter.** REG001 compares
a JSON-schema `properties` list against a signature; the call-based adopters carry
`input_model=<class>` instead of inline `parameters`, so `property_keys` is `None` and
REG001 is skipped regardless of correlation. REG002's name-correlation is exactly the
same-file boundary marker ADR-005 designed it to be. The handler-keyed change in this
ADR is confined to the **tier floor**, where landing on the real function matters; the
same-file model-parity check (REG010) correlates entry→`input_model`, not
entry→`def`, so it needs no handler correlation either (see ADR-012).

## Consequences

### Positive

- The "spec object → `register()` call" family (the adopter, Pydantic-AI, hand-rolled
  FastMCP wrappers) is extracted and checkable, turning REG/MCP rules from no-ops into
  working checks for that whole shape.
- Indirect, reused, deliberately-out-of-docstring descriptions participate in the
  Args-parsing rules — the contract a coding agent actually reads is the constant, and
  docpact now reads it too.
- The Tier 3 floor lands on the registered handler alone; adopters delete
  hand-maintained `per-file-tier = 3` overrides and the spurious findings they caused.
- No new config: existing `tool_definition_class` + field-map suffices.

### Negative

- The extractor grows from one shape (list elements) to four positions plus a
  constant table — more surface than a list walk, though all of it same-file and
  literal-bounded.
- Registry detection now fires on constructors outside list literals, including
  constructed-but-not-registered specs. Benign (literal-`name` guard, REG002-off) but
  a behavior change to record.
- Reproducing a function's tier by hand now also means scanning module-level builder
  calls and their `handler_ref`s, not just list literals — a wider (still same-file)
  input set for the floor.

### Neutral

- `registration_call` is reserved in `[tool.docpact.registry]`; the config schema is
  forward-compatible if it ships later.
- The one-hop, single-binding constant-resolution rule is fixed by this ADR and
  applies wherever a registry field takes a description string.

## Revisit triggers

1. **Class-name-anywhere over-matches in a real project** (a `ToolSpec`-named class
   used for non-registration purposes producing spurious entries) → ship the reserved
   `registration_call` key as the precision gate.
2. **A registration idiom appears that none of positions (a)–(d) cover** (e.g. a
   decorator-factory builder, or registration inside a module-level loop that is
   genuinely static) → re-evaluate the bounded-recursion rule for that shape.
3. **Demand to resolve multi-hop or assembled descriptions** with a precise,
   deterministic method → revisit the one-hop bright line (cf. DOC051's reserved
   status).
4. **Separated handlers need REG001 correlation** (an adopter carries both an inline
   `parameters` schema and a separate `handler_ref`) → extend REG001/REG002
   correlation to the handler, which Alternative E deferred.

## References

1. ADR-005 — same-file tool-registry validation (amended here: items 2 and 5; this
   realizes its revisit trigger #4)
2. ADR-009 — cross-file via LSP; ADR-012 — same-file REG010 in the default pass (the
   model-parity legs this extraction unlocks)
3. Spec §15.1 — registry config; §10.1 — tier floor; §8 — no-imports invariant
4. `src/docpact/parser/registry.py` — the extractor this ADR broadens
5. Originating request — an adopter project, `register_tool(ToolSpec(...))` surface

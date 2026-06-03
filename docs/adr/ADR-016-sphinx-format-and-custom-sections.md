# ADR-016: Sphinx/reST format with docpact-owned custom sections

**Status:** Accepted — deferred (unscheduled)
**Date:** 2026-06-03
**Deciders:** Ray
**Related:** ADR-001 (griffe), ADR-002 (format baseline), ADR-017 (reflective tool detection), spec §5.5, §7.1–§7.2, §8, §9

**Implementation status:** Not built. No spec cycle and no release is scheduled for
this. The design is recorded so a future session does not re-derive the feasibility
analysis (which is non-obvious — see Rationale). When it is built, it gets a phase in
PROGRESS.md and this status line is updated. See PROGRESS.md "Someday — designed, not
built."

## Context

docpact ships Google and NumPy docstring parsers (`format = "google" | "numpy"`),
both backed by griffe through one shared converter (`parser/docstring.py`). Sphinx/reST
was deferred "indefinitely" (spec §5.5, §8: "Sphinx is not on the roadmap") on the
stated grounds that modern Python projects no longer use it.

A feature request (motivated by Serena, an MCP coding-agent toolkit) challenged that
assumption: Serena documents its agent-facing tool methods in Sphinx/reST style
(`:param:`, `:return:`, `:raises:`), and those docstrings are the runtime contract from
which it generates MCP tool schemas. So the "nobody uses reST anymore" premise does not
hold for the agent-tool domain docpact targets.

The question this ADR answers: **if docpact adds a Sphinx parser, is it a thin griffe
wrapper (like NumPy was), or something larger — and what exactly does it have to own?**

## Decision

When built, docpact adds a `SphinxParser` selected by `format = "sphinx"` (with `"rest"`
as an accepted alias), with two parts:

1. **Core fields via griffe.** `griffe.parse_sphinx` handles `:param:` / `:type:` /
   `:return:` / `:rtype:` / `:raises:`. It emits the same `DocstringSectionKind` values
   (`parameters`, `returns`, `raises`, `text`) the existing `_sections_from_griffe`
   converter already consumes, and folds `:type x:` into the parameter annotation and
   `:rtype:` into the return — so DOC007 (param parity) and DOC022 (typed-prose
   mismatch) work with no rule changes.

2. **A docpact-owned section recovery pass** for the sections griffe's Sphinx parser
   does *not* produce but docpact's Tier 2/3 schema (§9, DOC012) requires —
   `Constraints`, `MCP`, `Mutates`, `Notes`, `See Also`, `Examples`. docpact recognizes
   these in a reST-idiomatic form and maps them to its canonical sections. The exact
   surface syntax is an implementation detail to settle when built; the working design
   is reST field-list entries (`:constraints:`, `:mcp:`, `:mutates:` with indented
   continuation) plus admonition directives (`.. note::`, `.. warning::` → `Notes`).
   The existing format-independent `Stability:` inline regex (`_STABILITY_RE`) already
   covers Stability and needs no Sphinx-specific work.

This is **not scheduled.** It is a design of record, revisable in place until built.

## Rationale

The empirical finding that makes this a real feature and not a 30-line wrapper
(measured against griffe 1.15.0, `griffe.parse_sphinx`):

- **The core works out of the box.** `:param`/`:type`/`:return`/`:rtype`/`:raises`
  parse into exactly the section kinds the shared converter expects. That half is as
  cheap as NumPy was.
- **Sphinx has no idiom griffe maps to docpact's custom sections.** A Google-style
  `Constraints:` block in a Sphinx docstring is **silently dropped** by `parse_sphinx`
  (it vanishes from the output entirely — not even retained as text). `.. note::`
  directives are **not parsed** as admonitions; they survive as raw text and, worse,
  bleed into the preceding field's description. Custom `:constraints:` / `:stability:`
  field entries are left as unrecognized raw text.

The consequence is decisive for why this is coupled to ADR-017: docpact's Tier 3 schema
*requires* Constraints, Stability, and MCP (DOC012, `docs/rules/DOC012.md`). With
griffe alone, **a Tier-3 Sphinx docstring is unsatisfiable** — the author has no way to
write a Constraints or MCP section that docpact will recognize. So "add Sphinx" without
the recovery pass would emit guaranteed-failing DOC012 findings on every Tier-3 Sphinx
function: pure noise. docpact must own the custom-section convention, or it should not
claim Tier-2/3 Sphinx support at all.

The parser abstraction (spec §7.2) already isolates this: the rule engine operates only
on `ParsedDocstring`, so all of the above is contained in one new parser class plus a
recovery pass, with zero rule changes.

## Alternatives considered

### Alternative A: Core fields only; document Tier 1–2 Sphinx, no custom sections

Ship the griffe-backed core, and document that Tiers 2/3 require Google/NumPy. Rejected
as the *committed* design because it strands exactly the use case that motivated the
request — agent-facing tools are precisely the Tier-3 functions, and they are where the
Constraints/MCP/Stability contract matters most. A Sphinx mode that can't express the
agent-tool contract is a half-feature. (It remains a legitimate *smaller* first
increment if the full design is ever scheduled and needs slicing — recorded here so
that option isn't lost.)

### Alternative B: griffe-only, accept whatever it parses

Rejected on the empirical findings above: griffe drops/garbles docpact's custom
sections under Sphinx. "Accept whatever it parses" means Tier-3 Sphinx is unsatisfiable
and `.. note::` content corrupts adjacent fields. Not viable.

### Alternative C: hand-roll a full reST parser

Rejected. The core field parsing is the bulk of the work and griffe does it correctly;
reimplementing it buys nothing and reintroduces the edge-case burden ADR-001 paid griffe
to absorb. docpact owns only the thin custom-section recovery layer.

## Consequences

### Positive
- Closes the format gap for the agent-tool domain docpact explicitly targets.
- Together with ADR-017, makes reflective Sphinx-documented tool surfaces (e.g. Serena)
  checkable at Tier 3 — the custom-section recovery is the exact gap that blocks that
  today.
- Reuses the existing parser seam and converter; no rule engine changes.

### Negative
- docpact owns a docpact-specific reST convention for custom sections. That is new
  surface to document, test, and keep stable, and it is *not* standard Sphinx — a reader
  using a real Sphinx renderer will see docpact's `:constraints:` field rendered as a
  generic field, not as docpact intends. Accepted: the same is already true of docpact's
  Google-style custom admonitions.
- A fourth format dilutes the "one opinionated baseline" stance (§8). Mitigated: NumPy
  already breached strict "one format," and the parser abstraction exists precisely for
  this.
- Inherits griffe's `parse_sphinx` quirks (trailing-text bleed into the last field).
  The recovery pass must run on the raw/cleaned text, not on griffe's output, to avoid
  the bleed — a known implementation constraint.

### Neutral
- `format_name()` gains `"sphinx"`; `_VALID_FORMATS` gains `"sphinx"` (and the `"rest"`
  alias normalizes to it). No change to JSON/text output contracts.

## Revisit triggers
- A real adopter (not a hypothetical) needs to run docpact on a Sphinx/reST codebase →
  schedule it, slicing via Alternative A if needed.
- griffe's `parse_sphinx` gains admonition parsing and stops dropping unknown blocks →
  the recovery pass shrinks; re-scope before building.
- ADR-017 is scheduled → these two ship together (the coupling above), or 017 explicitly
  caps Serena-style tools below Tier 3 to avoid the unsatisfiable-Constraints problem.

## References
- Feature request (Serena / Sphinx + class-based tool detection), 2026-06-03.
- Empirical `griffe.parse_sphinx` (1.15.0) behavior, recorded in this session.
- spec §9 (docstring schema), DOC012 (`docs/rules/DOC012.md`).

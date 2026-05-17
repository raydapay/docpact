# ADR-002: Docstring format baseline

**Status:** Accepted  
**Date:** 2026-05-17  
**Deciders:** [project leads]  
**Related:** Spec §5.1, §5.4, §7.2 (DocstringParser interface), §9 (Schema); ADR-001 (griffe dependency)

## Context

Python has at least three widely-used docstring conventions: Google, NumPy, and Sphinx (reStructuredText). Each is structurally different. A linter must choose which format(s) to support and in what order. The choice affects:

- Which projects can adopt docpact without first migrating their docstrings
- The complexity of the parser layer
- The shape of rules (sections vs. tags, prose vs. structured)
- How quickly v0.1 can ship

Supporting all formats from day one is appealing but increases v0.1 scope significantly. Supporting only one format risks excluding projects that already standardized on a different convention.

## Decision

**docpact v0.1 supports Google-style docstrings only. NumPy support is targeted for v0.2 via the parser abstraction described in spec §7.2. Sphinx support is not on the current roadmap.**

The configuration key `format = "google"` is already defined in the spec. It accepts `"numpy"` in v0.2 without configuration shape changes. The `"sphinx"` value is reserved but not committed.

## Rationale

**Google style is the de facto modern standard.** It is the style recommended by Google's Python style guide, adopted by mkdocstrings as its default parser, and widely used in newer Python codebases. It has section-based structure that is easy to parse and easy for humans to write correctly. It is the style FastMCP's documentation examples use and the style most MCP-adjacent codebases adopt.

**The parser layer is already abstracted.** Spec §7.2 defines `DocstringParser` as an interface with format-specific implementations. The rule engine operates on `ParsedDocstring` objects and has no knowledge of which format produced them. Adding NumPy or Sphinx parsing is contained work that does not require touching any rule.

**griffe supports all three.** Per ADR-001, griffe is the parsing foundation. griffe's Google, NumPy, and Sphinx parsers are all available. The constraint on v0.1 is the rule engine, not the parser — rules must be validated against each format's section conventions, and that validation is a one-format-at-a-time task.

**NumPy is a natural v0.2 follow-up.** NumPy style is dominant in scientific Python and machine learning code. Many high-value MCP server use cases (data tools, ML pipeline orchestration, scientific compute) live in NumPy-style codebases. Excluding NumPy permanently would meaningfully reduce the addressable user base.

**Sphinx is the longest tail.** Sphinx-style `:param:`/`:returns:` syntax is most common in older codebases and in projects that adopted reStructuredText for their documentation tooling. Modern projects rarely choose Sphinx style for new code. Supporting it costs parser implementation effort for a shrinking audience.

## Alternatives considered

### Alternative A: Support all three formats in v0.1

**Considered because.** It removes "wrong format" as an adoption blocker entirely. Any project can run docpact regardless of which convention it uses.

**Not chosen because.** Each format requires its own parser implementation and its own set of rule validations. Section names, entry formats, and ordering conventions differ. v0.1 would require validating that all rules work correctly across three formats. The work is roughly 2.5x the single-format effort, and v0.1 is already an ambitious scope.

### Alternative B: Auto-detect format per file

**Considered because.** Some projects mix styles. Auto-detection would handle this without configuration.

**Not chosen because.** Auto-detection is unreliable in adversarial cases (a file with a single short docstring may match multiple conventions). Mixed-style projects are an anti-pattern docpact should not encourage. Forcing a project-level choice via `format = "google"` is the right amount of friction.

### Alternative C: NumPy as v0.1 baseline instead of Google

**Considered because.** NumPy has stronger structural conventions (header underlines, more explicit section delimiters) which arguably makes it easier to parse correctly.

**Not chosen because.** Google's adoption in MCP-adjacent codebases is significantly higher. The audience docpact is designed for (FastMCP servers, agent-facing code, modern Python projects) is dominantly Google-style. Choosing the format with the larger overlap with the target audience is the right call for v0.1.

### Alternative D: Define a new docpact-specific format

**Considered briefly during early discussion** and immediately rejected. The relevant xkcd is #927. Introducing a new format to consolidate existing formats produces an additional format, not a consolidation.

## Consequences

### Positive

- v0.1 scope is bounded. One parser, one set of section-name validations, one set of fix patterns.
- Adoption is straightforward for the largest segment of the target audience.
- The parser abstraction is exercised by Google-only support; NumPy in v0.2 will validate the abstraction holds under a second concrete implementation.

### Negative

- NumPy-style projects cannot adopt docpact until v0.2. This excludes a significant fraction of scientific and ML Python codebases for one minor version cycle.
- Sphinx-style projects have no announced support timeline. Some users may need to migrate to Google before adopting docpact.

### Neutral

- The configuration shape (`format = "google"`) is set in v0.1 and remains valid through future versions.

## Revisit triggers

1. **NumPy v0.2 work uncovers parser-abstraction defects.** If supporting NumPy requires changes to `ParsedDocstring` or to rule signatures, the abstraction was incorrectly designed and needs rework. Document any changes in a new ADR.
2. **Sufficient user demand for Sphinx support.** Define "sufficient" as: more than ~10% of issues opened against docpact mention Sphinx, or two or more high-profile potential adopters specifically request it.
3. **A new format gains significant adoption.** If a new docstring convention emerges in the MCP/agent-tools ecosystem (this seems unlikely but is possible), evaluate whether to add it.

## References

1. [Google Python Style Guide — docstrings](https://google.github.io/styleguide/pyguide.html#383-functions-and-methods)
2. [NumPy docstring standard](https://numpydoc.readthedocs.io/en/latest/format.html)
3. [Sphinx info field lists](https://sphinx-doc.org/en/master/usage/domains/python.html#info-field-lists)
4. [griffe docstring parsers](https://mkdocstrings.github.io/griffe/reference/docstrings/)
5. [xkcd 927: Standards](https://xkcd.com/927/)

"""Output formatters.

Diagnostics are emitted in one of two formats in v0.1: text (human-readable)
or JSON (machine-readable). SARIF is planned for v0.2.

All formatters consume the same list[RuleResult] input. The CLI selects
the formatter based on --format.
"""

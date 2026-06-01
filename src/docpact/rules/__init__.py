"""Rule implementations.

Each rule is a pure function with signature:

    def check(
        func: FunctionInfo,
        doc: ParsedDocstring | None,
        config: RuleConfig,
    ) -> list[RuleResult]

Rules are organized by namespace:

- doc/  — DOC rules (structural docstring rules)
- mcp/  — MCP rules (MCP-specific validation)
- fix/  — FIX rules (fix-mode diagnostics)
- ty/   — TY rules (type/docstring cross-validation)

HEUR and SEM namespaces are reserved but not yet implemented.

The registry (_registry.py) maps rule codes to their implementing
functions. Rules self-register via @register on import. Call
load_builtin_rules() before any_rules() to ensure all built-in rules
are present.
"""

from __future__ import annotations

_BUILTIN_RULES_LOADED = False


def load_builtin_rules() -> None:
    """Import every built-in rule module so they register themselves.

    Idempotent — safe to call multiple times.
    """
    global _BUILTIN_RULES_LOADED
    if _BUILTIN_RULES_LOADED:
        return
    import docpact.rules.doc.doc001_missing_docstring
    import docpact.rules.doc.doc002_module_docstring
    import docpact.rules.doc.doc003_class_docstring
    import docpact.rules.doc.doc007_param_mismatch
    import docpact.rules.doc.doc012_missing_section
    import docpact.rules.doc.doc013_noncanonical_empty
    import docpact.rules.doc.doc014_suspicious_param
    import docpact.rules.doc.doc021_default_drift
    import docpact.rules.doc.doc022_type_prose_mismatch
    import docpact.rules.doc.doc050_pydantic_field
    import docpact.rules.doc.doc052_missing_examples
    import docpact.rules.doc.doc098_doctest_exception
    import docpact.rules.doc.doc099_fill_marker
    import docpact.rules.fix.fix001_bare_noqa
    import docpact.rules.fix.fix002_no_reason
    import docpact.rules.fix.fix003_stale_suppression
    import docpact.rules.fix.fix004_misplaced_suppression
    import docpact.rules.mcp.mcp001_decorator_docstring_conflict
    import docpact.rules.parse.parse001_syntax_error
    import docpact.rules.reg.reg001_schema_phantom_param
    import docpact.rules.reg.reg002_unmatched_entry
    import docpact.rules.reg.reg010_input_model_parity
    import docpact.rules.reg.reg011_handler_signature_parity
    import docpact.rules.sem.sem001_weak_docstring
    import docpact.rules.sem.sem002_weak_module_docstring
    import docpact.rules.ty.ty001_none_return_with_returns
    import docpact.rules.ty.ty002_nonnone_return_empty  # noqa: F401

    _BUILTIN_RULES_LOADED = True

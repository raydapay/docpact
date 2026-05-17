"""Rule implementations.

Each rule is a pure function with signature:

    def rule_XXXNNN(
        func: FunctionInfo,
        doc: ParsedDocstring | None,
        config: RuleConfig,
    ) -> list[RuleResult]

Rules are organized by namespace:

- doc/  — DOC rules (structural docstring rules)
- mcp/  — MCP rules (MCP-specific validation)
- fix/  — FIX rules (fix-mode diagnostics)

HEUR, TY, and SEM namespaces are reserved (spec §15.3) but not
implemented in v0.1.

The registry (see _registry.py) maps rule codes to their implementing
functions. Rules are discovered at startup, not registered manually.
"""

"""MCP001 — both decorator description= and docstring MCP: section present.

This is the strongest deterministic rule docpact provides. FastMCP
accepts both forms silently; if they have different content, the
runtime schema reflects whichever wins under FastMCP's parsing, and the
other form drifts unnoticed.

docpact reports MCP001 when both are present, regardless of whether
their content matches:
- If content is identical, --fix removes the docstring section (safe).
- If content differs, --unsafe-fixes removes the docstring section
  (decorator wins per opinionated posture).

See spec §10.4 (Tier 3), §11 (Fix Modes).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring


@register(
    RuleMetadata(
        code="MCP001",
        namespace="MCP",
        summary="Both decorator description= and docstring MCP: section present",
        default_severity=Severity.ERROR,
        fixable=True,  # safe when content is identical
        unsafe_fixable=True,  # decorator wins when content differs
    )
)
def check(
    func: FunctionInfo,
    doc: ParsedDocstring | None,
    config: RuleConfig,
) -> list[RuleResult]:
    """Detect simultaneous decorator and docstring MCP metadata."""
    return []  # Phase 7

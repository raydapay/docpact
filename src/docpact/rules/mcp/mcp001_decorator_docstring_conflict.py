"""MCP001 — Both decorator description= and docstring MCP: section present.

FastMCP reads MCP tool metadata from one of two places: the decorator's
description= keyword argument, or the docstring's MCP: section.  The
three states and their outcomes:

  1. Neither present → DOC012 fires (missing required MCP description).
  2. Exactly one present → OK.  Both forms are valid.  The decorator
     form (description=) is the FastMCP-recommended approach; the
     docstring MCP: section is the documentation-first alternative.
  3. Both present → MCP001 fires.  At runtime FastMCP's decorator
     description= takes precedence, but the MCP: section is kept for
     documentation purposes.  The conflict is flagged so the author can
     decide whether the two descriptions are intentionally different or
     have drifted out of sync.

No automated fix is provided: removing or merging the two descriptions
requires human judgment about which content is authoritative.

Severity is WARNING (default), reflecting that "both forms present" is
a maintenance concern rather than a structural error.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring

_MCP_DECORATOR_NAMES = frozenset(
    {
        "mcp.tool",
        "mcp.resource",
        "mcp.prompt",
        "tool",
        "resource",
        "prompt",
    }
)


@register(
    RuleMetadata(
        code="MCP001",
        namespace="MCP",
        summary="Both decorator description= and docstring MCP: section present",
        default_severity=Severity.WARNING,
        fixable=False,
        unsafe_fixable=False,
    )
)
def check(
    func: FunctionInfo,
    doc: ParsedDocstring | None,
    config: RuleConfig,
) -> list[RuleResult]:
    """Detect simultaneous decorator and docstring MCP metadata."""
    if doc is None:
        return []

    mcp_section = doc.sections.get("MCP")
    if mcp_section is None:
        return []

    decorator_desc: str | None = None
    for d in func.decorators:
        if d.name in _MCP_DECORATOR_NAMES and "description" in d.arguments:
            decorator_desc = d.arguments["description"]
            break

    if decorator_desc is None:
        return []

    return [
        RuleResult(
            code="MCP001",
            severity=config.severity,
            message="Both decorator description= and docstring MCP: section are present",
            location=SourceLocation(
                file_path=func.file_path,
                line=func.line,
                column=func.column,
            ),
        )
    ]

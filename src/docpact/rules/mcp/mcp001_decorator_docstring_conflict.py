"""MCP001 — Both decorator description= and docstring MCP: section present.

FastMCP accepts both forms silently; if they have different content, the
runtime schema reflects whichever wins under FastMCP's parsing, while the
other form drifts unnoticed. docpact reports MCP001 whenever both are
present so the conflict is caught before schema generation.

Fix behaviour:
  --fix           removes the docstring MCP: section when content is
                  identical (unambiguous deduplication).
  --unsafe-fixes  removes the docstring MCP: section when content
                  differs; the decorator wins because it is closer to
                  runtime behaviour.

Fix generation (section removal from the docstring raw text) is
planned; detection ships in v0.1.
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
        default_severity=Severity.ERROR,
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

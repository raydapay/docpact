"""DOC012 — Required docstring section missing for the function's tier.

A function that has a docstring but is missing one or more sections
required at its tier level triggers DOC012. Tier requirements:

  Tier 1: Summary only (no section requirements).
  Tier 2: Args (when params exist), Returns (when return is non-None).
  Tier 3+: same as Tier 2, plus Raises, Constraints, Stability, and
            either an MCP: docstring section or a decorator description=.

Sections marked None. (canonical empty form) pass this check. Only
entirely absent sections trigger DOC012.

No safe fix is available: the correct section content cannot be
inferred without semantic understanding of the function.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring

_MCP_DECORATORS = frozenset(
    {
        "mcp.tool",
        "mcp.resource",
        "mcp.prompt",
        "tool",
        "resource",
        "prompt",
    }
)


def _has_mcp_description(func: FunctionInfo) -> bool:
    return any(d.name in _MCP_DECORATORS and "description" in d.arguments for d in func.decorators)


def _has_non_none_return(func: FunctionInfo) -> bool:
    ra = func.return_annotation
    return bool(ra and ra.strip() not in ("None", ""))


@register(
    RuleMetadata(
        code="DOC012",
        namespace="DOC",
        summary="Required docstring section missing for function tier",
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
    """Check that all required sections are present for the function's tier."""
    if doc is None:
        return []

    tier = int(config.options.get("tier", 2))  # ty: ignore[invalid-argument-type]
    if tier <= 1:
        return []

    results: list[RuleResult] = []
    loc = SourceLocation(file_path=func.file_path, line=func.line, column=func.column)

    def _missing(section: str) -> None:
        results.append(
            RuleResult(
                code="DOC012",
                severity=config.severity,
                message=f"Tier {tier} function missing required section: {section}",
                location=loc,
            )
        )

    doc_params = [p for p in func.parameters if p.kind != "bound"]
    if doc_params and "Args" not in doc.sections:
        _missing("Args")

    if _has_non_none_return(func) and "Returns" not in doc.sections:
        _missing("Returns")

    if tier >= 3:
        for section in ("Raises", "Constraints", "Stability"):
            if section not in doc.sections:
                _missing(section)
        if "MCP" not in doc.sections and not _has_mcp_description(func):
            _missing("MCP")

    return results

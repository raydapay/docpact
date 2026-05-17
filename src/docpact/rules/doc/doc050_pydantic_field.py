"""DOC050 — Pydantic model field missing Field(description=...).

Fires when a Pydantic model class has an annotated field that lacks a
Field(description=...) call. Field-level documentation belongs in
Field(description=...) rather than in the using function's Args section.

Deferred: detection requires class-level AST analysis to identify Pydantic
models and inspect their fields. The current rule engine operates on
function definitions only. Class-level analysis is planned for Phase 8.
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
        code="DOC050",
        namespace="DOC",
        summary="Pydantic model field missing Field(description=...)",
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
    """Check Pydantic model fields for Field(description=...) — deferred."""
    return []  # Phase 8: requires class-level analysis

"""DOC013 — Empty docstring section uses non-canonical form.

The canonical form for a section with nothing to document is "None."
(a single sentence explicitly stating absence). Non-canonical forms
include blank bodies, "N/A", "None" without the trailing period, and
equivalent abbreviations. The safe fix replaces the body with "None.".

Only fires for sections that griffe parsed and stored with a non-canonical
body. Structured sections (Args, Raises) whose content griffe cannot parse
are typically dropped silently; those are caught by DOC012 instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring

_NON_CANONICAL: frozenset[str] = frozenset({"n/a", "na", "none", ""})


@register(
    RuleMetadata(
        code="DOC013",
        namespace="DOC",
        summary="Empty section uses non-canonical form; should be 'None.'",
        default_severity=Severity.WARNING,
        fixable=True,
        unsafe_fixable=False,
    )
)
def check(
    func: FunctionInfo,
    doc: ParsedDocstring | None,
    config: RuleConfig,
) -> list[RuleResult]:
    """Check that empty sections use the canonical 'None.' form."""
    if doc is None:
        return []

    results: list[RuleResult] = []
    loc = SourceLocation(file_path=func.file_path, line=func.line, column=func.column)

    for name, section in doc.sections.items():
        if section.entries:
            continue
        body = (section.body or "").strip()
        if body == "None.":
            continue
        if body.lower() in _NON_CANONICAL:
            results.append(
                RuleResult(
                    code="DOC013",
                    severity=config.severity,
                    message=f"Section '{name}' uses non-canonical empty form; use 'None.' instead",
                    location=loc,
                )
            )

    return results

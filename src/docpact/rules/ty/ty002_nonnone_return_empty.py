"""TY002 — Returns section is canonically empty but return annotation is non-None.

Fires when a function has a non-None return annotation yet its docstring
contains a Returns section whose body is the canonical empty form
("None."). The annotation promises a value; the section explicitly
documents nothing. DOC012 is satisfied (the section exists), so the
contradiction goes undetected without this rule.

Unannotated functions are excluded: DOC012 handles the missing-section
case for them at the appropriate tier.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring


def _has_non_none_return(func: FunctionInfo) -> bool:
    """Return True when the function has an explicit non-None return annotation.

    Args:
        func: Function metadata to inspect.

    Returns:
        True if the annotation is present and not 'None'.
    """
    ra = func.return_annotation
    return bool(ra and ra.strip() not in ("None", ""))


@register(
    RuleMetadata(
        code="TY002",
        namespace="TY",
        summary="Returns section is 'None.' but return annotation is non-None",
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
    """Check that a non-None-annotated function does not use an empty Returns section.

    Args:
        func: Function metadata including the return annotation.
        doc: Parsed docstring, or None if absent.
        config: Rule configuration including severity override.

    Returns:
        List containing one diagnostic if the contradiction is detected,
        empty otherwise.
    """
    if doc is None:
        return []
    if not _has_non_none_return(func):
        return []

    returns_section = doc.sections.get("Returns")
    if returns_section is None:
        return []

    body = (returns_section.body or "").strip()
    if body != "None.":
        return []

    annotation = func.return_annotation or ""
    return [
        RuleResult(
            code="TY002",
            severity=config.severity,
            message=f"Returns section is 'None.' but return annotation is '{annotation.strip()}'",
            location=SourceLocation(
                file_path=func.file_path,
                line=func.line,
                column=func.column,
            ),
        )
    ]

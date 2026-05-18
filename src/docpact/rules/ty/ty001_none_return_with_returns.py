"""TY001 — Returns section present but return annotation is None.

Fires when a function is explicitly annotated ``-> None`` yet its
docstring contains a Returns section with substantive content. The
section claims the function returns a value; the annotation says it
does not. One of them is wrong.

Canonical-empty Returns sections (body is a None-equivalent: "None.",
"None", "N/A", etc.) do not trigger this rule — those express the
absence of a return value explicitly and are structurally correct, if
redundant.

Unannotated functions are excluded: the annotation may simply be
missing, so the contradiction cannot be confirmed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring, Section

_EMPTY_BODIES: frozenset[str] = frozenset({"none.", "none", "n/a", "na", ""})


def _returns_has_content(section: Section) -> bool:
    """Return True when the Returns section body is substantive (not empty/None-equivalent).

    Args:
        section: The Returns section to inspect.

    Returns:
        True if body contains real descriptive content.
    """
    body = (section.body or "").strip().lower()
    return body not in _EMPTY_BODIES


@register(
    RuleMetadata(
        code="TY001",
        namespace="TY",
        summary="Returns section present but return annotation is 'None'",
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
    """Check that a None-annotated function does not document a return value.

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
    if func.return_annotation is None:
        return []
    if func.return_annotation.strip() != "None":
        return []

    returns_section = doc.sections.get("Returns")
    if returns_section is None:
        return []
    if not _returns_has_content(returns_section):
        return []

    return [
        RuleResult(
            code="TY001",
            severity=config.severity,
            message="Return annotation is 'None' but Returns section documents a value",
            location=SourceLocation(
                file_path=func.file_path,
                line=func.line,
                column=func.column,
            ),
        )
    ]

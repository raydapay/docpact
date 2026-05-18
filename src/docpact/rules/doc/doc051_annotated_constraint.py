"""DOC051 — Docstring Constraints section duplicates Annotated metadata.

Any constraint expressible in Annotated[T, ...] or Pydantic Field(...)
belongs in the type annotation, not in the Constraints prose. When the
Constraints section repeats a value already encoded in the annotation
(length limit, numeric range, pattern, etc.), DOC051 fires.

Detection strategy (v0.1): extract numeric values from common Annotated
metadata functions (MaxLen, MinLen, Ge, Le, Gt, Lt, max_length, etc.)
and check whether the Constraints body contains those values. This
heuristic catches the most common duplication patterns.

The safe fix removes the duplicating prose entry from the Constraints
section. Fix generation is deferred; detection ships in v0.1.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring

_ANNOTATED_RE = re.compile(r"\bAnnotated\[")

# Matches common constraint metadata calls with a numeric argument.
# Captures: (keyword, value, closing_paren_or_empty)
# Call form:  MaxLen(4096) → group(1)=MaxLen, group(2)=4096, group(3)=)
# Kwarg form: max_length=4096 → group(1)=max_length, group(2)=4096, group(3)=''
_CONSTRAINT_CALL_RE = re.compile(
    r"\b(MaxLen|MinLen|Ge|Le|Gt|Lt|max_length|min_length|max_digits|min_digits)"
    r"\s*[=(]\s*(\d+)\s*(\))?"
)


@register(
    RuleMetadata(
        code="DOC051",
        namespace="DOC",
        summary="Constraints section duplicates Annotated metadata",
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
    """Check that Constraints prose does not duplicate Annotated metadata."""
    if doc is None:
        return []

    constraints_section = doc.sections.get("Constraints")
    if constraints_section is None:
        return []

    constraints_body = (constraints_section.body or "").strip()
    if not constraints_body or constraints_body == "None.":
        return []

    results: list[RuleResult] = []
    loc = SourceLocation(file_path=func.file_path, line=func.line, column=func.column)
    reported: set[str] = set()

    for param in func.parameters:
        if not param.annotation or not _ANNOTATED_RE.search(param.annotation):
            continue
        for m in _CONSTRAINT_CALL_RE.finditer(param.annotation):
            value = m.group(2)
            call_text = m.group(0)  # includes closing ) when present
            if value in constraints_body and call_text not in reported:
                reported.add(call_text)
                results.append(
                    RuleResult(
                        code="DOC051",
                        severity=config.severity,
                        message=f"Constraint duplicates Annotated metadata: {call_text!r}",
                        location=loc,
                    )
                )

    return results

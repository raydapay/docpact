"""DOC014 — Documented parameter name looks like a typo of a real parameter.

Fires when a documented parameter name is absent from the signature but
closely resembles a real parameter (edit distance 1-2, similarity >= 0.6).
This is a warning-level hint; the exact fix cannot be determined without
knowing whether the parameter was renamed, the docstring was wrong, or
both.

DOC007 fires alongside DOC014 when the phantom entry also counts as a
strict signature mismatch. DOC014 adds the "likely typo" hint that
DOC007 does not emit.

No fix is available.
"""

from __future__ import annotations

from difflib import get_close_matches
from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring


@register(
    RuleMetadata(
        code="DOC014",
        namespace="DOC",
        summary="Documented parameter name is a likely typo of a real parameter",
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
    """Check for documented parameter names that are close matches to real parameters."""
    if doc is None:
        return []

    args_section = doc.sections.get("Args")
    if args_section is None or not args_section.entries:
        return []

    documented = {e.key.lstrip("*") for e in args_section.entries}
    valid = {p.name for p in func.parameters if p.kind != "bound"}

    results: list[RuleResult] = []
    loc = SourceLocation(file_path=func.file_path, line=func.line, column=func.column)

    for phantom in sorted(documented - valid):
        matches = get_close_matches(phantom, valid, n=1, cutoff=0.6)
        if matches:
            results.append(
                RuleResult(
                    code="DOC014",
                    severity=config.severity,
                    message=f"Parameter {phantom!r} not in signature; did you mean {matches[0]!r}?",
                    location=loc,
                )
            )

    return results

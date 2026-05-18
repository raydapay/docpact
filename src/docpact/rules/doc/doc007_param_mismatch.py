"""DOC007 — Args section inconsistent with function signature.

Two sub-cases, both reported as DOC007:
  1. A positional/keyword parameter appears in the signature but is absent
     from the Args section.  Only fires at Tier 2+ (Tier 1 treats Args as
     recommended, not required).
  2. An entry in the Args section names a parameter that does not exist in
     the signature (phantom parameter — likely a rename that was missed).
     Fires at all tiers.

var_positional (*args) and var_keyword (**kwargs) are optional to document
(spec §9.1: "documented when their contents are meaningful"), so their
absence from Args does not trigger sub-case 1.  If documented, their names
must still match (sub-case 2 applies).

No fix is available: the mismatch is ambiguous — docpact cannot determine
whether a parameter was renamed, removed, or simply forgotten.  DOC014
provides a warning-level hint when a likely typo is detected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring


@register(
    RuleMetadata(
        code="DOC007",
        namespace="DOC",
        summary="Args section inconsistent with function signature",
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
    """Check Args section consistency with the function signature."""
    if doc is None:
        return []

    args_section = doc.sections.get("Args")
    if args_section is None:
        return []

    # Parse the documented parameter set.
    # Griffe preserves leading '*'/'**' on var_positional/var_keyword names
    # (e.g. "*args"), but FunctionInfo.name is the bare name ("args").
    # Strip leading '*' so both sides of the comparison use bare names.
    documented: set[str] = (
        {e.key.lstrip("*") for e in args_section.entries}
        if args_section.entries
        else set()  # body="None." — explicit empty form
    )

    # Parameters that MUST appear in Args: positional and keyword only.
    # Bound (self/cls), var_positional (*args), and var_keyword (**kwargs)
    # are excluded from the mandatory set.
    required: set[str] = {p.name for p in func.parameters if p.kind in ("positional", "keyword")}

    # Parameters valid to document: everything except the bound receiver.
    valid: set[str] = {p.name for p in func.parameters if p.kind != "bound"}

    tier = int(config.options.get("tier", 2))  # ty: ignore[invalid-argument-type]
    results: list[RuleResult] = []
    loc = SourceLocation(file_path=func.file_path, line=func.line, column=func.column)

    # Sub-case 1: required param in signature but absent from Args.
    # Only at Tier 2+ where Args is required.
    if tier >= 2:
        for name in sorted(required - documented):
            results.append(
                RuleResult(
                    code="DOC007",
                    severity=config.severity,
                    message=f"Parameter {name!r} present in signature but absent from Args",
                    location=loc,
                )
            )

    # Sub-case 2: entry in Args names no real parameter (phantom).
    # Fires at all tiers — a phantom entry is always wrong.
    for name in sorted(documented - valid):
        results.append(
            RuleResult(
                code="DOC007",
                severity=config.severity,
                message=f"Parameter {name!r} documented in Args but absent from signature",
                location=loc,
            )
        )

    return results

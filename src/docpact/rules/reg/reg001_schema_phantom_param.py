"""REG001 — tool-registry schema names a parameter absent from the signature.

DOC007's phantom-parameter sub-case, lifted from the docstring ``Args:`` section
to the programmatic tool schema. Fires when a ``parameters.properties`` key in a
same-file tool-registry entry (a ``ToolDefinition(...)`` constructor or a
``{"name": ..., "parameters": {...}}`` dict literal) names a parameter that the
registered function's signature does not have — typically a rename applied to the
signature and docstring but missed in the schema, leaving the LLM describing a
parameter that no longer exists.

This is a *consistency* check, not a *completeness* check: like DOC007's phantom
sub-case it fires at all tiers. Its applicability is gated by whether a function
has a matching same-file registry entry, not by tier.

Same-file only (ADR-005). An entry whose ``name`` matches no function in the file
is not handled here — that is REG002's concern. Entries whose ``parameters`` is
not a static dict literal (``property_keys is None``) are skipped: the schema is
built dynamically and the keys cannot be enumerated, the same literals-only
discipline DOC021 applies to default values.

This is a file-level rule. The CLI runs check_registry_phantom_params directly
with the file's functions and extracted entries; the registered check function is
a no-op stub that keeps REG001 visible in list-rules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from pathlib import Path

    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring
    from docpact.model.tool_registry import ToolRegistryEntry


@register(
    RuleMetadata(
        code="REG001",
        namespace="REG",
        summary="Tool-registry schema names a parameter absent from the signature",
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
    """REG001 is file-level; all parameters unused. See check_registry_phantom_params."""
    return []


def check_registry_phantom_params(
    functions: list[FunctionInfo],
    entries: list[ToolRegistryEntry],
    file_path: Path,
    config: RuleConfig,
) -> list[RuleResult]:
    """Emit REG001 for each schema property key absent from its function signature.

    Args:
        functions: All functions defined in the file (FunctionInfo, source order).
        entries: Tool-registry entries extracted from the same file.
        file_path: Path to the source file (for SourceLocation).
        config: Rule configuration including severity.

    Returns:
        One RuleResult per phantom property key, located at the registry entry.
        Entries with no matching function, or whose parameters are not a static
        dict literal, contribute nothing.

    Constraints:
        Correlation is by exact name match against module-level functions in the
        same file. No cross-file resolution. Deterministic: results are sorted by
        location then parameter name.
    """
    # Valid parameter names per module-level function (the bound receiver is not a
    # schema-exposable parameter, so it is excluded — matching DOC007's `valid` set).
    valid_by_name: dict[str, set[str]] = {
        f.name: {p.name for p in f.parameters if p.kind != "bound"}
        for f in functions
        if f.containing_class is None
    }

    results: list[RuleResult] = []
    for entry in entries:
        if entry.property_keys is None:
            continue  # dynamic schema — cannot enumerate (literals-only)
        valid = valid_by_name.get(entry.name)
        if valid is None:
            continue  # unmatched entry — REG002's concern, not REG001's
        for key in sorted(entry.property_keys - valid):
            results.append(
                RuleResult(
                    code="REG001",
                    severity=config.severity,
                    message=(
                        f"Tool-registry schema for {entry.name!r} documents parameter "
                        f"{key!r}, which is absent from the function signature"
                    ),
                    location=SourceLocation(
                        file_path=file_path,
                        line=entry.line,
                        column=entry.column,
                    ),
                )
            )

    results.sort(key=lambda r: (r.location.line, r.location.column, r.message))
    return results

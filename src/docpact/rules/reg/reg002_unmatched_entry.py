"""REG002 — tool-registry entry names no function in the same file.

A coverage-visibility diagnostic, **off by default**. When a registry entry's
``name`` matches no function defined in the same file, docpact cannot cross-check
it (the function is presumably registered from another module — the cross-file
pattern that is out of scope per ADR-005). By default such an entry is silently
skipped, which keeps the per-file boundary honest without noise.

Teams that want to audit how much of their registry is actually covered can opt
in by raising REG002's severity, e.g.::

    [tool.docpact.rules]
    REG002 = "warning"

It is then suppressible per line with ``# nodo: REG002 -- reason`` like any rule.
REG002 carries ``default_severity = OFF`` because docpact has only ERROR / WARNING
/ OFF severities (no INFO tier); OFF is how "present but silent until opted into"
is expressed.

This is a file-level rule. The CLI runs check_unmatched_entries directly with the
file's functions and extracted entries; the registered check function is a no-op
stub that keeps REG002 visible in list-rules.
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
        code="REG002",
        namespace="REG",
        summary="Tool-registry entry names no function in the same file",
        default_severity=Severity.OFF,
        fixable=False,
        unsafe_fixable=False,
    )
)
def check(
    func: FunctionInfo,
    doc: ParsedDocstring | None,
    config: RuleConfig,
) -> list[RuleResult]:
    """REG002 is file-level; all parameters unused. See check_unmatched_entries."""
    return []


def check_unmatched_entries(
    functions: list[FunctionInfo],
    entries: list[ToolRegistryEntry],
    file_path: Path,
    config: RuleConfig,
) -> list[RuleResult]:
    """Emit REG002 for each registry entry not matching a same-file function.

    Args:
        functions: All functions defined in the file (FunctionInfo, source order).
        entries: Tool-registry entries extracted from the same file.
        file_path: Path to the source file (for SourceLocation).
        config: Rule configuration including severity.

    Returns:
        One RuleResult per entry whose name matches no module-level function in
        the file, located at the entry. Empty when every entry is matched.

    Constraints:
        Matching is by exact name against module-level functions in the same
        file. No cross-file resolution is attempted — that is the boundary this
        rule exists to surface.
    """
    module_func_names = {f.name for f in functions if f.containing_class is None}
    results: list[RuleResult] = []
    for entry in entries:
        if entry.name in module_func_names:
            continue
        results.append(
            RuleResult(
                code="REG002",
                severity=config.severity,
                message=(
                    f"Tool-registry entry {entry.name!r} matches no function in this file; "
                    "cross-file registration is not cross-checked"
                ),
                location=SourceLocation(
                    file_path=file_path,
                    line=entry.line,
                    column=entry.column,
                ),
            )
        )
    results.sort(key=lambda r: (r.location.line, r.location.column))
    return results

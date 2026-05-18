"""DOC003 — Missing docstring on a class definition.

Fires when a class body does not begin with a string literal. Applies to
all class definitions in the file: top-level classes, nested classes, and
inner classes. Empty-bodied classes (only ``pass`` or ``...``) are not
exempt — even a one-line summary helps readers understand intent.

Disable for specific files (generated code, stubs, migration scripts) via
per-file-ignores:

    [tool.docpact.per-file-ignores]
    "src/generated/**/*.py" = ["DOC003"]

Or suppress inline on the ``class`` keyword line:

    class LegacyHelper(  # nodo: DOC003 -- grandfathered, refactor tracked in #99
        Base,
    ):

This is a file-level rule. The CLI's source scan calls check_class_docstrings
directly; the registered check function is a no-op stub that keeps DOC003
visible in list-rules.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from pathlib import Path

    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring


@register(
    RuleMetadata(
        code="DOC003",
        namespace="DOC",
        summary="Missing docstring on a class definition",
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
    """DOC003 is file-level; all parameters unused. See check_class_docstrings."""
    return []


def check_class_docstrings(
    source: str,
    file_path: Path,
    config: RuleConfig,
) -> list[RuleResult]:
    """Emit DOC003 for each class in the file that has no docstring.

    Args:
        source: Full source text of the file.
        file_path: Path to the source file (for SourceLocation).
        config: Rule configuration including severity.

    Returns:
        One RuleResult per undocumented class, in source order. Files that
        fail to parse are silently skipped.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    results: list[RuleResult] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        has_docstring = (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        )
        if not has_docstring:
            results.append(
                RuleResult(
                    code="DOC003",
                    severity=config.severity,
                    message=f"Class '{node.name}' has no docstring",
                    location=SourceLocation(
                        file_path=file_path,
                        line=node.lineno,
                        column=node.col_offset,
                    ),
                )
            )

    results.sort(key=lambda r: (r.location.line, r.location.column))
    return results

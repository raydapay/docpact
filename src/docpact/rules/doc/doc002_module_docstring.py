"""DOC002 — Missing module-level docstring.

Fires when a Python file has no module docstring. A module docstring is the
first statement of the file when that statement is a string literal. Blank
files, pure namespace packages, and `__init__.py` files that only re-export
symbols technically satisfy PEP 257 with no docstring, but for agent-facing
code a module docstring is the fastest way to signal intent and scope.

Disable for pure namespace packages or generated modules via per-file-ignores:

    [tool.docpact.per-file-ignores]
    "src/mypkg/__init__.py" = ["DOC002"]

This is a file-level rule, not a function-level rule. The CLI's source scan
calls check_module_docstring directly; the registered check function is a
no-op stub that keeps DOC002 visible in list-rules.
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
        code="DOC002",
        namespace="DOC",
        summary="Missing module-level docstring",
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
    """DOC002 is file-level; all parameters unused. See check_module_docstring."""
    return []


def check_module_docstring(
    source: str,
    file_path: Path,
    config: RuleConfig,
) -> list[RuleResult]:
    """Emit DOC002 when a file has no module-level docstring.

    Args:
        source: Full source text of the file.
        file_path: Path to the source file (for SourceLocation).
        config: Rule configuration including severity.

    Returns:
        A single RuleResult at line 1 if the module has no docstring; empty
        list otherwise. Empty files and files that fail to parse are silently
        skipped — a parse error will surface via other means.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    if not tree.body:
        return []  # completely empty file — nothing to document

    has_docstring = (
        isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    )
    if has_docstring:
        return []

    return [
        RuleResult(
            code="DOC002",
            severity=config.severity,
            message="Module has no docstring",
            location=SourceLocation(
                file_path=file_path,
                line=1,
                column=0,
            ),
        )
    ]

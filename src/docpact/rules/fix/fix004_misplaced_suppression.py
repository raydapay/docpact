"""FIX004 — Suppression comment is not on a def keyword line.

docpact matches suppression comments by func.line — the line of the ``def``
keyword. A suppression placed on any other line is parsed into the suppression
map but silently ignored: no diagnostic fires on that line, so nothing is
actually suppressed, and the original violation keeps firing.

The most common cause is ruff's formatter. When it wraps a function signature,
it moves trailing comments from the ``def`` line to the closing ``) -> Type:``
line. To survive ruff reformatting, place the suppression after the opening
parenthesis:

    def foo(  # nodo: DOC012 -- reason
        arg: str,
    ) -> None: ...

Not:

    def foo(
        arg: str,
    ) -> None:  # nodo: DOC012 -- reason  ← ruff puts it here; silently ignored

This is a file-level rule. The registered check function is a no-op stub.
check_misplaced_suppressions is called directly by the CLI after parse_suppressions.
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
        code="FIX004",
        namespace="FIX",
        summary="Suppression comment is not on a `def` keyword line; will be silently ignored",
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
    """FIX004 is file-level; all parameters unused. See check_misplaced_suppressions."""
    return []


def check_misplaced_suppressions(
    source: str,
    suppressions: dict[int, frozenset[str]],
    file_path: Path,
    config: RuleConfig,
) -> list[RuleResult]:
    """Emit FIX004 for each suppression comment not on a def/class/module line.

    Args:
        source: Full source text of the file being checked.
        suppressions: Per-line suppression map from parse_suppressions.
        file_path: Path to the source file (for SourceLocation).
        config: Rule configuration including severity.

    Returns:
        One RuleResult per misplaced suppression line, in line order.
        Returns empty list if source cannot be parsed (PARSE001 owns that path).

    Constraints:
        A suppression is considered correctly placed when it is on a ``def``
        keyword line, an ``async def`` keyword line, a ``class`` keyword line,
        or line 1 (module-level, for DOC002). Any other placement is flagged.

    Stability: beta
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    valid_lines: set[int] = {1}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            valid_lines.add(node.lineno)

    results: list[RuleResult] = []
    lines = source.splitlines()
    for lineno, _codes in sorted(suppressions.items()):
        if lineno in valid_lines:
            continue
        line_text = lines[lineno - 1] if lineno <= len(lines) else ""
        col = line_text.find("#")
        stripped = line_text.strip()
        if stripped.startswith(")") and "->" in stripped:
            hint = (
                " (looks like ruff moved it from the `def` line to the closing `) -> Type:` line)"
            )
        else:
            hint = ""
        results.append(
            RuleResult(
                code="FIX004",
                severity=config.severity,
                message=(
                    "Suppression comment is not on a `def` keyword line;"
                    f" it will be silently ignored{hint}"
                ),
                location=SourceLocation(
                    file_path=file_path,
                    line=lineno,
                    column=max(col, 0),
                ),
            )
        )

    return results

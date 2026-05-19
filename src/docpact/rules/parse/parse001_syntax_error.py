"""PARSE001 — File contains a Python syntax error and cannot be parsed.

This rule fires when a file fails to parse entirely. All other rules are
skipped for the file — structural analysis requires a valid AST.

PARSE001 is wired as a file-level rule in _run_checks; the registered
check function is a no-op stub that keeps PARSE001 visible in list-rules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from pathlib import Path

    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring


@register(
    RuleMetadata(
        code="PARSE001",
        namespace="PARSE",
        summary="File contains a Python syntax error and cannot be parsed",
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
    """Stub — PARSE001 is wired as a file-level rule in _run_checks."""
    return []


def check_syntax_error(
    exc: SyntaxError,
    file_path: Path,
    config: RuleConfig,
) -> RuleResult:
    """Emit a PARSE001 diagnostic from a SyntaxError raised during parsing.

    Args:
        exc: The SyntaxError raised by extract_functions. Uses exc.msg for
            the message text and exc.lineno / exc.offset for position.
        file_path: Path to the source file; forwarded to SourceLocation.
        config: Rule configuration, used to read the effective severity.

    Returns:
        A single RuleResult with code PARSE001 at the error position.

    Raises:
        None — all attribute accesses on SyntaxError are guarded for None.

    Stability: beta
    """
    line = exc.lineno if exc.lineno is not None else 1
    column = (exc.offset - 1) if exc.offset is not None and exc.offset > 0 else 0
    return RuleResult(
        code="PARSE001",
        severity=config.severity,
        message=exc.msg,
        location=SourceLocation(
            file_path=file_path,
            line=line,
            column=column,
        ),
    )

"""FIX001 — Bare # noqa comment without specific rule codes.

Bare # noqa (no code list) suppresses every docpact diagnostic on the
line. This makes the suppression opaque to reviewers — it is impossible
to tell which rule was being suppressed or why. Every suppression should
name the specific code(s) and include a -- reason.

This is a line-level rule, not a function-level rule. The CLI's source
scan calls check_bare_noqa directly after parse_suppressions; the
registered check function is a no-op stub that keeps FIX001 visible in
list-rules.

Good:   # noqa: DOC001 -- pre-docpact legacy, tracked in #412
Bad:    # noqa
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
        code="FIX001",
        namespace="FIX",
        summary="Bare # noqa without specific rule codes",
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
    """FIX001 is line-level; see check_bare_noqa for the actual implementation.

    Args:
        func: The function being checked (unused; FIX001 is file-level).
        doc: Parsed docstring (unused; FIX001 is file-level).
        config: Rule configuration (unused; FIX001 is file-level).

    Returns:
        Always empty; the real checks run via check_bare_noqa.
    """
    return []


def check_bare_noqa(
    source: str,
    suppressions: dict[int, frozenset[str]],
    file_path: Path,
    config: RuleConfig,
) -> list[RuleResult]:
    """Emit FIX001 for each bare # noqa line (empty code set).

    Args:
        source: Full source text of the file being checked.
        suppressions: Per-line suppression map from parse_suppressions.
        file_path: Path to the source file (for SourceLocation).
        config: Rule configuration including severity.

    Returns:
        One RuleResult per bare noqa line.
    """
    results: list[RuleResult] = []
    lines = source.splitlines()
    for lineno, codes in suppressions.items():
        if codes:
            continue
        line = lines[lineno - 1] if lineno <= len(lines) else ""
        col = line.find("#")
        results.append(
            RuleResult(
                code="FIX001",
                severity=config.severity,
                message="Bare # noqa suppresses all rules; add specific codes and a -- reason",
                location=SourceLocation(
                    file_path=file_path,
                    line=lineno,
                    column=max(col, 0),
                ),
            )
        )
    return results

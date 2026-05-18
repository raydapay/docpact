"""FIX002 — Inline suppression names codes but has no -- reason.

Every suppression that names specific codes should also document why the
suppression is correct. A bare code (`# nodo: DOC001`) tells reviewers what
was suppressed but not why — the same information gap that makes bare
suppressions (FIX001) opaque.

Good:   # nodo: DOC001 -- pre-docpact legacy, tracked in #412
Bad:    # nodo: DOC001   (no -- reason clause → FIX002)

The `-- reason` separator is two hyphens followed by at least one non-
whitespace character. Whitespace between the code list and `--` is allowed.

This is a line-level rule. The CLI's source scan calls check_no_reason
directly; the registered check function is a no-op stub that keeps FIX002
visible in list-rules.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from pathlib import Path

    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring


@register(
    RuleMetadata(
        code="FIX002",
        namespace="FIX",
        summary="Suppression names codes but has no -- reason",
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
    """FIX002 is line-level; all parameters unused. See check_no_reason."""
    return []


def _build_reason_re(markers: tuple[str, ...]) -> re.Pattern[str]:
    """Match a suppression with codes; group(1) captures the reason text if present."""
    alternation = "|".join(re.escape(m) for m in markers)
    return re.compile(
        rf"#\s*(?:{alternation}):\s*[A-Z][A-Z0-9]*(?:\s*,\s*[A-Z][A-Z0-9]*)*"
        r"(?:\s+--\s+(\S.*))?$"
    )


def check_no_reason(
    source: str,
    suppressions: dict[int, frozenset[str]],
    file_path: Path,
    config: RuleConfig,
    markers: tuple[str, ...] = ("nodo",),
) -> list[RuleResult]:
    """Emit FIX002 for each suppression that names codes but omits a -- reason.

    Args:
        source: Full source text of the file being checked.
        suppressions: Per-line suppression map from parse_suppressions.
        file_path: Path to the source file (for SourceLocation).
        config: Rule configuration including severity.
        markers: Marker words recognised as suppressions (must match those
            passed to parse_suppressions for the same file).

    Returns:
        One RuleResult per line that has a named-code suppression without
        a -- reason. Lines with bare suppressions (FIX001 territory) are
        skipped here.
    """
    pattern = _build_reason_re(markers)
    lines = source.splitlines()
    results: list[RuleResult] = []

    for lineno, codes in suppressions.items():
        if not codes:
            continue  # bare suppression — FIX001's domain, not ours
        line = lines[lineno - 1] if lineno <= len(lines) else ""
        m = pattern.search(line)
        if m is None:
            continue
        if m.group(1) is None:  # no reason text after --
            col = line.find("#")
            results.append(
                RuleResult(
                    code="FIX002",
                    severity=config.severity,
                    message="Suppression has no reason; add -- reason after the code list",
                    location=SourceLocation(
                        file_path=file_path,
                        line=lineno,
                        column=max(col, 0),
                    ),
                )
            )
    return results

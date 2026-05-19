"""FIX003 — Suppression comment names a code with no active violation on this line.

After the ``--add-suppression`` baselining workflow, docstrings get written
and violations are fixed. But the ``# nodo: CODE -- baseline`` comments
added during baselining are never automatically removed — they accumulate
as dead weight and obscure which suppressions are still load-bearing.

FIX003 is the mechanical complement to ``--add-suppression``: it fires
whenever a suppression comment names a code that has *no active violation*
on that line. Deleting the comment (or the specific code from a multi-code
comment) is the correct resolution.

This is a file-level post-pass rule. It runs after all other rules have
been evaluated for the file, so it can compare the suppression map against
the complete set of violations produced for that file. The registered
``check`` function is a no-op stub; the CLI calls ``check_stale_suppressions``
directly.

Bare suppressions (``# nodo`` with no codes) are excluded — FIX001 handles
those.

No auto-fix. Removing a suppression comment requires knowing which code(s)
in a multi-code comment are stale; that determination is unambiguous but
the edit is non-trivial when codes need to be pruned rather than the whole
comment deleted. This may be added as a safe fix in a future release.
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
        code="FIX003",
        namespace="FIX",
        summary="Suppression comment names a code with no active violation on this line",
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
    """FIX003 is a file-level post-pass; all parameters unused. See check_stale_suppressions."""
    return []


def check_stale_suppressions(
    source: str,
    suppressions: dict[int, frozenset[str]],
    violations: list[RuleResult],
    file_path: Path,
    config: RuleConfig,
) -> list[RuleResult]:
    """Emit FIX003 for each suppression code with no matching active violation.

    Args:
        source: Full source text of the file being checked.
        suppressions: Per-line suppression map from parse_suppressions.
        violations: All violations collected for this file before suppression
            filtering is applied. FIX003 fires when none of these match.
        file_path: Path to the source file (for SourceLocation).
        config: Rule configuration including severity.

    Returns:
        One RuleResult per stale (code, line) pair, in line order.
        Bare suppressions (empty code sets) are skipped — FIX001 owns those.

    Constraints:
        Must run after all other rules for the file have been collected.
        The violations list must not yet have suppression filtering applied,
        otherwise active violations suppressed by other comments would appear
        stale here.

    Stability: beta
    """
    active: frozenset[tuple[int, str]] = frozenset((r.location.line, r.code) for r in violations)

    results: list[RuleResult] = []
    lines = source.splitlines()
    for lineno, codes in sorted(suppressions.items()):
        if not codes:
            continue
        for code in sorted(codes):
            if (lineno, code) in active:
                continue
            line_text = lines[lineno - 1] if lineno <= len(lines) else ""
            col = line_text.find("#")
            results.append(
                RuleResult(
                    code="FIX003",
                    severity=config.severity,
                    message=f"Suppression of {code!r} is unused — no active violation on this line",
                    location=SourceLocation(
                        file_path=file_path,
                        line=lineno,
                        column=max(col, 0),
                    ),
                )
            )

    return results

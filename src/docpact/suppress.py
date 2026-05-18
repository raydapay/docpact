"""Inline suppression parsing.

Handles inline suppression comments per spec §15.2. The default marker word
is ``nodo`` (``# nodo: CODE``), configurable via ``suppress_comment`` in
pyproject.toml. Suppressions are evaluated after rules run; they filter
diagnostics before output and exit-code calculation. Fixes are still applied
to suppressed diagnostics.

Syntax (default marker ``nodo``):
    # nodo: DOC001
    # nodo: DOC001, DOC007
    # nodo: DOC001 -- optional reason text

Bare marker (without codes) suppresses all diagnostics on that line and
is itself a violation of FIX001.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from docpact.model.diagnostic import RuleResult


def _build_re(markers: tuple[str, ...]) -> re.Pattern[str]:
    """Build a suppression comment regex for the given marker words."""
    alternation = "|".join(re.escape(m) for m in markers)
    return re.compile(rf"#\s*(?:{alternation})(?::\s*([A-Z][A-Z0-9]*(?:\s*,\s*[A-Z][A-Z0-9]*)*))?")


def parse_suppressions(
    source: str,
    *,
    markers: tuple[str, ...] = ("nodo",),
) -> dict[int, frozenset[str]]:
    """Parse all suppression comments from source text.

    Args:
        source: Full source text of a Python file.
        markers: Marker words to recognise (e.g. ``("nodo",)`` or
            ``("nodo", "noqa")``). Case-sensitive.

    Returns:
        Mapping of 1-based line number to suppressed code set. An empty
        frozenset means a bare marker (suppress all codes on that line).
    """
    pattern = _build_re(markers)
    result: dict[int, frozenset[str]] = {}
    for lineno, line in enumerate(source.splitlines(), start=1):
        m = pattern.search(line)
        if m is None:
            continue
        codes_str = m.group(1)
        if codes_str is None:
            result[lineno] = frozenset()  # bare suppression
        else:
            result[lineno] = frozenset(c.strip() for c in codes_str.split(","))
    return result


def is_suppressed(
    result: RuleResult,
    file_suppressions: dict[int, frozenset[str]],
) -> bool:
    """Return True if a diagnostic is suppressed by an inline suppression comment.

    Args:
        result: The diagnostic to check.
        file_suppressions: Suppression map from parse_suppressions for the
            same file.

    Returns:
        True when the result's (line, code) matches a suppression entry.
    """
    line_codes = file_suppressions.get(result.location.line)
    if line_codes is None:
        return False
    return len(line_codes) == 0 or result.code in line_codes


def apply_suppressions(
    results: list[RuleResult],
    suppressions: dict[Path, dict[int, frozenset[str]]],
) -> list[RuleResult]:
    """Filter suppressed diagnostics from a result list.

    Args:
        results: All diagnostics from the rule engine.
        suppressions: Per-file suppression maps, keyed by absolute path.

    Returns:
        Filtered list with suppressed entries removed.
    """
    return [r for r in results if not is_suppressed(r, suppressions.get(r.location.file_path, {}))]

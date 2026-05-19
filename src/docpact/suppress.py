"""Inline suppression parsing.

Handles inline suppression comments per spec §15.2. The default marker word
is ``nodo`` (``# nodo: CODE``), configurable via ``suppress_comment`` in
pyproject.toml. Suppressions are evaluated after rules run; they filter
diagnostics before output and exit-code calculation. Fixes are still applied
to suppressed diagnostics.

Syntax (default marker ``nodo``):
    # nodo: DOC001 -- reason text
    # nodo: DOC001, DOC007 -- reason text
    # nodo: DOC001 -- optional reason text

Bare marker (without codes) suppresses all diagnostics on that line and
is itself a violation of FIX001.

Scanner implementation:
    ``parse_suppressions`` uses ``tokenize.generate_tokens`` to walk the
    token stream rather than a raw line scan. This guarantees that suppression
    patterns inside string literals (module docstrings, inline strings) are
    never treated as real suppressions — ``tokenize`` only emits ``COMMENT``
    tokens for actual Python comments, never for text inside strings.

Why the regex is built per call rather than as a module-level constant:
    ``suppress_comment`` is a per-project config value, not a global. A
    module-level regex would bake in ``nodo`` at import time and break any
    project that configures a different marker. ``_build_re`` compiles the
    pattern once per ``parse_suppressions`` call — negligible cost, correct
    semantics.
"""

from __future__ import annotations

import io
import re
import tokenize
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

    Constraints:
        Suppression must appear on the ``def`` keyword line, not on the
        closing ``) -> None:`` line. docpact matches by ``func.line`` (the
        line of the ``def`` keyword). ruff's formatter moves trailing comments
        to ``) -> None:`` when it wraps signatures — use ``def foo(  # nodo:``
        (after the opening paren) to keep the comment on the ``def`` line.
    """
    pattern = _build_re(markers)
    result: dict[int, frozenset[str]] = {}
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in tokens:
            if tok.type != tokenize.COMMENT:
                continue
            m = pattern.search(tok.string)
            if m is None:
                continue
            lineno = tok.start[0]  # 1-based, matches existing convention
            codes_str = m.group(1)
            if codes_str is None:
                result[lineno] = frozenset()  # bare suppression
            else:
                result[lineno] = frozenset(c.strip() for c in codes_str.split(","))
    except tokenize.TokenError:
        # Unclosed string or other tokenize-level error (broken source).
        # Return partial results — caller handles parse failures separately.
        pass
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
        True when the diagnostic's line has a suppression entry that covers
        its code (or a bare entry that covers all codes). False when the line
        has no entry or the code is not listed.
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
        Subset of results for which no suppression applies; preserves input order.
    """
    return [r for r in results if not is_suppressed(r, suppressions.get(r.location.file_path, {}))]

"""Suppression baselining — --add-suppression implementation.

Given a list of visible diagnostics, inserts ``# nodo: CODE -- reason``
comments at the diagnostic's source line. Merges with any existing
suppression comment on the same line, preserving the existing reason.

FIX001 and FIX002 are always skipped: adding suppression comments for
suppression-hygiene rules would be recursive.
"""

from __future__ import annotations

import difflib
import re
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from docpact.model.diagnostic import RuleResult

# Codes excluded from baselining — suppression-hygiene rules are recursive.
_SKIP_CODES: frozenset[str] = frozenset({"FIX001", "FIX002"})


def _build_pattern(markers: tuple[str, ...]) -> re.Pattern[str]:
    """Build a regex that matches an existing suppression comment on a line.

    Args:
        markers: Suppression marker words (e.g. ``("nodo",)``).

    Returns:
        Pattern with two optional groups: (1) the code list string, (2) the
        reason text after ``--``.
    """
    alternation = "|".join(re.escape(m) for m in markers)
    return re.compile(
        rf"#\s*(?:{alternation})(?::\s*([A-Z][A-Z0-9]*(?:\s*,\s*[A-Z][A-Z0-9]*)*))?"
        r"(?:\s+--\s+(.+))?"
    )


def _patch_line(
    line: str,
    new_codes: frozenset[str],
    reason: str,
    markers: tuple[str, ...],
    pattern: re.Pattern[str],
) -> str:
    """Return the line with new_codes merged into any existing suppression comment.

    Args:
        line: A single source line, including the trailing newline if present.
        new_codes: Rule codes to add to the line's suppression comment.
        reason: Default reason text; used only when no existing reason is found.
        markers: Suppression marker words.
        pattern: Pre-compiled pattern from _build_pattern.

    Returns:
        Modified line. Unchanged if a bare suppression already covers everything.
    """
    m = pattern.search(line)

    if m is None:
        # No existing suppression — append a new comment.
        nl = "\n" if line.endswith("\n") else ""
        codes_str = ", ".join(sorted(new_codes))
        return f"{line.rstrip(chr(10))}  # {markers[0]}: {codes_str} -- {reason}{nl}"

    # Bare marker (no codes) already suppresses everything — nothing to add.
    codes_group = m.group(1)
    if codes_group is None:
        return line

    existing_codes = frozenset(c.strip() for c in codes_group.split(",") if c.strip())
    if not (new_codes - existing_codes):
        return line  # all new codes already present

    all_codes = sorted(existing_codes | new_codes)
    codes_str = ", ".join(all_codes)

    # Preserve the existing reason; fall back to the caller-supplied reason.
    existing_reason = (m.group(2) or "").strip()
    kept_reason = existing_reason if existing_reason else reason

    comment_start = m.start()
    prefix = line[:comment_start].rstrip()
    nl = "\n" if line.endswith("\n") else ""
    return f"{prefix}  # {markers[0]}: {codes_str} -- {kept_reason}{nl}"


def _group_by_file_line(
    results: list[RuleResult],
) -> dict[Path, dict[int, frozenset[str]]]:
    """Group diagnostic codes by file path and 1-based line number.

    Args:
        results: Diagnostics from the rule engine.

    Returns:
        Nested mapping: file_path → line_number → frozenset of codes.
        FIX001 and FIX002 are excluded.
    """
    grouped: dict[Path, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    for r in results:
        if r.code in _SKIP_CODES:
            continue
        grouped[r.location.file_path][r.location.line].add(r.code)
    return {
        fp: {ln: frozenset(codes) for ln, codes in by_line.items()}
        for fp, by_line in grouped.items()
    }


def add_suppressions(
    results: list[RuleResult],
    reason: str = "baseline",
    markers: tuple[str, ...] = ("nodo",),
) -> dict[Path, int]:
    """Add suppression comments in-place for each visible diagnostic.

    Args:
        results: Visible diagnostics to baseline.
        reason: Reason text appended after ``--`` in each new suppression.
        markers: Suppression marker words. ``markers[0]`` is used for new
            comments.

    Returns:
        Mapping of modified file path to the number of lines where suppression
        comments were added or expanded. Files with no changes are omitted.

    Constraints:
        FIX001 and FIX002 are always skipped. Files that cannot be read or
        written due to OS errors are silently omitted from the return dict.

    Stability: beta
    """
    grouped = _group_by_file_line(results)
    if not grouped:
        return {}

    pattern = _build_pattern(markers)
    counts: dict[Path, int] = {}

    for file_path, line_codes in grouped.items():
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        lines = source.splitlines(keepends=True)
        changed = 0

        for lineno, new_codes in sorted(line_codes.items()):
            if lineno < 1 or lineno > len(lines):
                continue
            idx = lineno - 1
            original = lines[idx]
            patched = _patch_line(original, new_codes, reason, markers, pattern)
            if patched != original:
                lines[idx] = patched
                changed += 1

        if changed:
            try:
                file_path.write_text("".join(lines), encoding="utf-8")
            except OSError:
                continue
            counts[file_path] = changed

    return counts


def diff_suppressions(
    results: list[RuleResult],
    reason: str = "baseline",
    markers: tuple[str, ...] = ("nodo",),
) -> str:
    """Return a unified diff of suppression additions without writing files.

    Args:
        results: Visible diagnostics to baseline.
        reason: Reason text appended after ``--`` in each new suppression.
        markers: Suppression marker words. ``markers[0]`` is used for new
            comments.

    Returns:
        Unified diff string; empty string if there are no changes to make.

    Stability: beta
    """
    grouped = _group_by_file_line(results)
    if not grouped:
        return ""

    pattern = _build_pattern(markers)
    parts: list[str] = []

    for file_path, line_codes in sorted(grouped.items(), key=lambda kv: str(kv[0])):
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        original_lines = source.splitlines(keepends=True)
        modified_lines = list(original_lines)

        for lineno, new_codes in sorted(line_codes.items()):
            if lineno < 1 or lineno > len(modified_lines):
                continue
            idx = lineno - 1
            modified_lines[idx] = _patch_line(
                modified_lines[idx], new_codes, reason, markers, pattern
            )

        if modified_lines != original_lines:
            parts.append(
                "".join(
                    difflib.unified_diff(
                        original_lines,
                        modified_lines,
                        fromfile=f"a/{file_path}",
                        tofile=f"b/{file_path}",
                    )
                )
            )

    return "".join(parts)

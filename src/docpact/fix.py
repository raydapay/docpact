"""Fix engine.

Applies Fix objects to source files in-place. Consumers pass the list of
RuleResult objects; this module extracts the fix/unsafe_fix payloads, checks
for conflicts, and either writes the patched bytes or returns a unified diff.

Design invariants:
- Fixes are applied end-to-start within each file so that byte offsets of
  earlier fixes remain valid after later (higher-offset) fixes are applied.
- Two fixes conflict when their byte ranges overlap. Conflicting fixes are
  reported but never silently dropped — the caller decides how to surface them.
- The engine never imports analyzed code and never runs sub-processes.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from docpact.model.diagnostic import Fix, RuleResult


@dataclass(frozen=True, slots=True)
class ConflictError:
    """Two fixes targeting overlapping byte ranges in the same file."""

    file_path: Path
    first: Fix
    second: Fix

    def __str__(self) -> str:
        return (
            f"{self.file_path}: conflicting fixes at "
            f"[{self.first.start_offset}, {self.first.end_offset}) and "
            f"[{self.second.start_offset}, {self.second.end_offset})"
        )


def _overlaps(a: Fix, b: Fix) -> bool:
    """Return True when two fixes have overlapping byte ranges."""
    return a.start_offset < b.end_offset and b.start_offset < a.end_offset


def _collect_fixes(
    results: list[RuleResult],
    apply_unsafe: bool,
) -> list[Fix]:
    """Extract Fix objects from rule results.

    Args:
        results: Diagnostics from the rule engine.
        apply_unsafe: When True, include unsafe_fix payloads as well.

    Returns:
        All applicable Fix objects deduplicated by (file, start, end).
    """
    seen: set[tuple[Path, int, int]] = set()
    fixes: list[Fix] = []
    for r in results:
        candidates = [r.fix] if r.fix is not None else []
        if apply_unsafe and r.unsafe_fix is not None:
            candidates.append(r.unsafe_fix)
        for fix in candidates:
            key = (fix.file_path, fix.start_offset, fix.end_offset)
            if key not in seen:
                seen.add(key)
                fixes.append(fix)
    return fixes


def _group_by_file(fixes: list[Fix]) -> dict[Path, list[Fix]]:
    groups: dict[Path, list[Fix]] = {}
    for fix in fixes:
        groups.setdefault(fix.file_path, []).append(fix)
    return groups


def _check_conflicts(fixes: list[Fix]) -> list[ConflictError]:
    """Return all pairwise conflicts in a list of fixes for one file.

    Args:
        fixes: Fixes for a single file, in any order.

    Returns:
        List of ConflictError for each overlapping pair found.
    """
    sorted_fixes = sorted(fixes, key=lambda f: f.start_offset)
    errors: list[ConflictError] = []
    for i, a in enumerate(sorted_fixes):
        for b in sorted_fixes[i + 1 :]:
            if b.start_offset >= a.end_offset:
                break  # sorted — no further overlaps possible
            errors.append(ConflictError(file_path=a.file_path, first=a, second=b))
    return errors


def _apply_to_bytes(source: bytes, fixes: list[Fix]) -> bytes:
    """Apply a conflict-free set of fixes to source bytes.

    Args:
        source: Original file contents as bytes.
        fixes: Fixes for this file; must be conflict-free.

    Returns:
        Patched file contents.
    """
    # Apply end-to-start so earlier offsets remain valid.
    for fix in sorted(fixes, key=lambda f: f.start_offset, reverse=True):
        patch = fix.replacement.encode()
        source = source[: fix.start_offset] + patch + source[fix.end_offset :]
    return source


def apply_fixes(
    results: list[RuleResult],
    *,
    unsafe: bool = False,
) -> tuple[list[Path], list[ConflictError]]:
    """Apply fixes from rule results to source files in-place.

    Args:
        results: Diagnostics produced by the rule engine.
        unsafe: When True, also apply unsafe_fix payloads.

    Returns:
        Tuple of (modified_paths, conflicts). modified_paths lists every file
        that was written. conflicts lists any overlapping fix pairs that were
        skipped — each conflict leaves both fixes unapplied for that file.
    """
    fixes = _collect_fixes(results, apply_unsafe=unsafe)
    groups = _group_by_file(fixes)

    modified: list[Path] = []
    all_conflicts: list[ConflictError] = []

    for file_path, file_fixes in sorted(groups.items()):
        conflicts = _check_conflicts(file_fixes)
        if conflicts:
            all_conflicts.extend(conflicts)
            continue

        source = file_path.read_bytes()
        patched = _apply_to_bytes(source, file_fixes)
        if patched != source:
            file_path.write_bytes(patched)
            modified.append(file_path)

    return modified, all_conflicts


def diff_fixes(
    results: list[RuleResult],
    *,
    unsafe: bool = False,
) -> str:
    """Return a unified diff of what --fix would apply, without writing files.

    Args:
        results: Diagnostics produced by the rule engine.
        unsafe: When True, include unsafe_fix payloads in the diff.

    Returns:
        Unified diff string. Empty string when there is nothing to change.
    """
    fixes = _collect_fixes(results, apply_unsafe=unsafe)
    groups = _group_by_file(fixes)

    diff_parts: list[str] = []

    for file_path, file_fixes in sorted(groups.items()):
        conflicts = _check_conflicts(file_fixes)
        if conflicts:
            continue  # skip conflicting files, same as apply_fixes

        source_bytes = file_path.read_bytes()
        patched_bytes = _apply_to_bytes(source_bytes, file_fixes)
        if patched_bytes == source_bytes:
            continue

        source_lines = source_bytes.decode(errors="replace").splitlines(keepends=True)
        patched_lines = patched_bytes.decode(errors="replace").splitlines(keepends=True)
        path_str = str(file_path)
        diff = difflib.unified_diff(
            source_lines,
            patched_lines,
            fromfile=path_str,
            tofile=path_str,
        )
        diff_parts.append("".join(diff))

    return "".join(diff_parts)

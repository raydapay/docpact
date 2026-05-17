"""Output formatters.

Diagnostics are emitted in one of two formats in v0.1: text (human-readable)
or JSON (machine-readable). SARIF is planned for v0.2.

All formatters consume the same list[RuleResult] input. The CLI selects
the formatter based on --format.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from docpact.model.diagnostic import RuleResult


def format_text(results: list[RuleResult], cwd: Path | None = None) -> str:
    """Format diagnostics as human-readable text.

    Each result produces one line:
        path:line:col: CODE [*] message

    The [*] marker appears when a safe fix is available.  A help line
    follows when a fix description exists:
        = help: description

    Args:
        results: Diagnostics to format, in any order.
        cwd: Working directory used to make file paths relative.
            When None the paths are left as-is.

    Returns:
        Formatted string, empty when results is empty.
    """
    if not results:
        return ""

    lines: list[str] = []
    for r in results:
        path = r.location.file_path
        if cwd is not None:
            with contextlib.suppress(ValueError):
                path = path.relative_to(cwd)

        fixable = " [*]" if r.fix is not None else ""
        lines.append(f"{path}:{r.location.line}:{r.location.column}: {r.code}{fixable} {r.message}")
        if r.fix is not None:
            lines.append(f"  = help: {r.fix.description}")

    return "\n".join(lines)


def format_summary(results: list[RuleResult]) -> str:
    """Return the 'Found N errors (M fixable)' summary line.

    Args:
        results: All collected diagnostics.

    Returns:
        Single summary sentence, or empty string when results is empty.
    """
    if not results:
        return ""

    n = len(results)
    fixable = sum(1 for r in results if r.fix is not None)
    unsafe = sum(1 for r in results if r.unsafe_fix is not None)

    noun = "error" if n == 1 else "errors"
    msg = f"Found {n} {noun}"

    parts: list[str] = []
    if fixable:
        parts.append(f"{fixable} fixable with --fix")
    if unsafe:
        parts.append(f"{unsafe} fixable with --unsafe-fixes")

    if parts:
        msg += f" ({', '.join(parts)})"
    msg += "."
    return msg

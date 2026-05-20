"""Output formatters.

Diagnostics are emitted in three formats: text (human-readable), JSON
(machine-readable), and SARIF 2.1.0 (static-analysis interchange).

All formatters consume the same list[RuleResult] input. The CLI selects
the formatter based on --format.

Why a single module rather than text.py / json.py / sarif.py:
    At three small functions the split would be premature. If a fourth
    formatter lands, that is the natural trigger to split.
"""

from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from docpact.model.diagnostic import RuleResult, Severity

_JSON_VERSION = "1"
_SARIF_SCHEMA = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
)


def _sarif_level(severity: Severity) -> str:
    """Map a docpact Severity to a SARIF level string.

    Args:
        severity: The severity value to convert.

    Returns:
        One of "error", "warning", or "note".
    """
    from docpact.model.diagnostic import Severity as S

    if severity == S.ERROR:
        return "error"
    if severity == S.WARNING:
        return "warning"
    return "note"


def format_text(
    results: list[RuleResult],
    cwd: Path | None = None,
    color: bool = False,
) -> str:
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
        color: When True, apply ANSI colors via rich: error codes in
            red, warning codes in yellow, fix markers in cyan, help
            lines dimmed.

    Returns:
        Formatted string, empty when results is empty.
    """
    if not results:
        return ""

    if color:
        return _format_text_color(results, cwd)

    lines: list[str] = []
    for r in results:
        path_str = r.location.file_path.as_posix()
        if cwd is not None:
            with contextlib.suppress(ValueError):
                path_str = r.location.file_path.relative_to(cwd).as_posix()

        fixable = " [*]" if r.fix is not None else ""
        lines.append(
            f"{path_str}:{r.location.line}:{r.location.column}: {r.code}{fixable} {r.message}"
        )
        if r.fix is not None:
            lines.append(f"  = help: {r.fix.description}")

    return "\n".join(lines)


def _format_text_color(results: list[RuleResult], cwd: Path | None) -> str:
    """Render diagnostics with ANSI color via rich."""
    import io

    from rich.console import Console
    from rich.text import Text

    from docpact.model.diagnostic import Severity

    sio = io.StringIO()
    # width=10000 prevents rich from wrapping long lines.
    console = Console(file=sio, highlight=False, no_color=False, width=10000)

    for r in results:
        path_str = r.location.file_path.as_posix()
        if cwd is not None:
            with contextlib.suppress(ValueError):
                path_str = r.location.file_path.relative_to(cwd).as_posix()

        code_style = "bold red" if r.severity == Severity.ERROR else "bold yellow"

        line = Text()
        line.append(f"{path_str}:{r.location.line}:{r.location.column}: ")
        line.append(r.code, style=code_style)
        if r.fix is not None:
            line.append(" [*]", style="bold cyan")
        line.append(f" {r.message}")
        console.print(line, end="\n")

        if r.fix is not None:
            help_line = Text()
            help_line.append("  = help: ", style="dim")
            help_line.append(r.fix.description, style="dim")
            console.print(help_line, end="\n")

    output = sio.getvalue()
    # Console adds a trailing newline per print; strip to match format_text convention.
    return output.rstrip("\n")


def format_json(results: list[RuleResult], cwd: Path | None = None) -> str:
    """Format diagnostics as a versioned JSON document.

    Schema version "1". Top-level keys: version, diagnostics, summary.
    Each diagnostic has: code, severity, message, location (file, line,
    column), fixable, unsafe_fixable.

    Args:
        results: Diagnostics to format, in any order.
        cwd: Working directory used to make file paths relative.
            When None the paths are left as-is.

    Returns:
        JSON string. Always valid JSON, even when results is empty.
    """
    diagnostics = []
    for r in results:
        path_str = r.location.file_path.as_posix()
        if cwd is not None:
            with contextlib.suppress(ValueError):
                path_str = r.location.file_path.relative_to(cwd).as_posix()
        diagnostics.append(
            {
                "code": r.code,
                "severity": str(r.severity),
                "message": r.message,
                "location": {
                    "file": path_str,
                    "line": r.location.line,
                    "column": r.location.column,
                },
                "fixable": r.fix is not None,
                "unsafe_fixable": r.unsafe_fix is not None,
            }
        )

    n = len(results)
    fixable = sum(1 for r in results if r.fix is not None)
    unsafe = sum(1 for r in results if r.unsafe_fix is not None)

    doc = {
        "version": _JSON_VERSION,
        "diagnostics": diagnostics,
        "summary": {"total": n, "fixable": fixable, "unsafe_fixable": unsafe},
    }
    return json.dumps(doc, indent=2)


def format_sarif(results: list[RuleResult], cwd: Path | None = None) -> str:
    """Format diagnostics as a SARIF 2.1.0 JSON document.

    Produces a single-run SARIF document. The driver.rules array is
    populated from the live rule registry. Artifact URIs are relative
    (with uriBaseId "%SRCROOT%") when cwd is provided, absolute
    file:// URIs otherwise.

    Args:
        results: Diagnostics to format, in any order.
        cwd: Working directory used as the SARIF %SRCROOT% base. When
            provided, file paths inside cwd become relative URIs and
            originalUriBaseIds is populated. Paths outside cwd fall back
            to absolute file:// URIs.

    Returns:
        SARIF 2.1.0 JSON string. Always valid JSON, even when results is
        empty.
    """
    import importlib.metadata

    from docpact.rules._registry import all_rules

    try:
        version = importlib.metadata.version("docpact")
    except importlib.metadata.PackageNotFoundError:
        version = "0.0.0"

    rules_snapshot = all_rules()
    driver_rules = [
        {
            "id": code,
            "shortDescription": {"text": meta.summary},
            "defaultConfiguration": {"level": _sarif_level(meta.default_severity)},
        }
        for code, (meta, _) in sorted(rules_snapshot.items())
    ]

    sarif_results = []
    for r in results:
        path = r.location.file_path
        artifact: dict[str, str]
        if cwd is not None:
            try:
                rel = path.relative_to(cwd)
                artifact = {"uri": rel.as_posix(), "uriBaseId": "%SRCROOT%"}
            except ValueError:
                artifact = {"uri": path.as_uri()}
        else:
            artifact = {"uri": path.as_uri()}

        sarif_results.append(
            {
                "ruleId": r.code,
                "level": _sarif_level(r.severity),
                "message": {"text": r.message},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": artifact,
                            # SARIF columns are 1-based; docpact stores 0-based.
                            "region": {
                                "startLine": r.location.line,
                                "startColumn": r.location.column + 1,
                            },
                        }
                    }
                ],
            }
        )

    run: dict[str, object] = {
        "tool": {
            "driver": {
                "name": "docpact",
                "version": version,
                "rules": driver_rules,
            }
        },
        "results": sarif_results,
    }

    if cwd is not None:
        run["originalUriBaseIds"] = {"%SRCROOT%": {"uri": cwd.absolute().as_uri() + "/"}}

    return json.dumps(
        {"version": "2.1.0", "$schema": _SARIF_SCHEMA, "runs": [run]},
        indent=2,
    )


def format_github(results: list[RuleResult], cwd: Path | None = None) -> str:
    """Format diagnostics as GitHub Actions workflow commands.

    Emits ``::error`` or ``::warning`` annotations that GitHub Actions parses
    as inline PR and commit annotations. No upload step required — pipe the
    output directly to the Actions log.

    Args:
        results: Diagnostics to format.
        cwd: Working directory used to make file paths relative.
            When None the paths are left as-is.

    Returns:
        Newline-joined annotation lines. Empty string when results is empty.
    """
    if not results:
        return ""

    from docpact.model.diagnostic import Severity

    lines: list[str] = []
    for r in results:
        path_str = r.location.file_path.as_posix()
        if cwd is not None:
            with contextlib.suppress(ValueError):
                path_str = r.location.file_path.relative_to(cwd).as_posix()
        level = "error" if r.severity == Severity.ERROR else "warning"
        # GitHub annotation syntax uses :: as delimiter; escape any occurrences in the message.
        message = r.message.replace("::", "%3A%3A")
        col = r.location.column + 1  # GitHub uses 1-based columns
        lines.append(
            f"::{level} file={path_str},line={r.location.line},col={col},title={r.code}::{message}"
        )
    return "\n".join(lines)


def format_statistics(results: list[RuleResult]) -> str:
    """Format a per-rule violation count table.

    Each line shows the count, rule code, and rule summary, sorted by count
    descending (ties broken by code alphabetically).

    Args:
        results: Diagnostics to count.

    Returns:
        Multi-line string, one rule per line. Empty string when results is empty.
    """
    if not results:
        return ""

    from docpact.rules._registry import all_rules

    rules = all_rules()

    counts: dict[str, int] = {}
    for r in results:
        counts[r.code] = counts.get(r.code, 0) + 1

    sorted_counts = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    width = len(str(sorted_counts[0][1]))

    lines: list[str] = []
    for code, count in sorted_counts:
        summary = rules[code][0].summary if code in rules else ""
        lines.append(f"{count:{width}}  {code}  {summary}")

    return "\n".join(lines)


def format_suppress_hint(suppress_marker: str) -> str:
    """Return a one-line footer hint showing the suppression syntax.

    Args:
        suppress_marker: The configured suppression keyword (e.g. "nodo").

    Returns:
        Hint string, always non-empty.
    """
    return (
        f"hint: to suppress a violation: # {suppress_marker}: CODE -- reason"
        "  (or --add-suppression to baseline all)"
    )


def format_summary(results: list[RuleResult]) -> str:
    """Return a summary line counting errors and warnings separately.

    Args:
        results: All collected diagnostics.

    Returns:
        Single summary sentence, or empty string when results is empty.
    """
    if not results:
        return ""

    from docpact.model.diagnostic import Severity

    errors = sum(1 for r in results if r.severity == Severity.ERROR)
    warnings = sum(1 for r in results if r.severity == Severity.WARNING)
    fixable = sum(1 for r in results if r.fix is not None)
    unsafe = sum(1 for r in results if r.unsafe_fix is not None)

    parts: list[str] = []
    if errors:
        parts.append(f"{errors} {'error' if errors == 1 else 'errors'}")
    if warnings:
        parts.append(f"{warnings} {'warning' if warnings == 1 else 'warnings'}")

    msg = "Found " + ", ".join(parts)

    fix_parts: list[str] = []
    if fixable:
        fix_parts.append(f"{fixable} fixable with --fix")
    if unsafe:
        fix_parts.append(f"{unsafe} fixable with --unsafe-fixes")
    if fix_parts:
        msg += f" ({', '.join(fix_parts)})"

    msg += "."
    return msg

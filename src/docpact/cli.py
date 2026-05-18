"""CLI entry point.

Implements the commands defined in spec §16: check, generate, show-schema,
list-rules. v0.1 ships with check (including --fix and --unsafe-fixes) as
the primary surface.

Implementation notes:
    Uses click for subcommands. argparse was considered (stdlib, no
    dependencies) but click's ergonomics for subcommands with shared options
    are materially better for a tool with this command surface.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click

import docpact.rules.doc.doc001_missing_docstring
import docpact.rules.doc.doc002_module_docstring
import docpact.rules.doc.doc003_class_docstring
import docpact.rules.doc.doc007_param_mismatch
import docpact.rules.doc.doc012_missing_section
import docpact.rules.doc.doc013_noncanonical_empty
import docpact.rules.doc.doc014_suspicious_param
import docpact.rules.doc.doc050_pydantic_field
import docpact.rules.doc.doc051_annotated_constraint
import docpact.rules.doc.doc098_doctest_exception
import docpact.rules.doc.doc099_fill_marker
import docpact.rules.fix.fix001_bare_noqa
import docpact.rules.fix.fix002_no_reason
import docpact.rules.mcp.mcp001_decorator_docstring_conflict  # noqa: F401
from docpact.config import Config, file_ignores_for, file_is_excluded, load_config, rule_is_enabled
from docpact.fix import apply_fixes, diff_fixes
from docpact.output import format_json, format_summary, format_text
from docpact.parser.docstring import GoogleParser, NumpyParser
from docpact.parser.source import extract_functions
from docpact.rules._registry import RuleConfig, all_rules
from docpact.rules.doc.doc002_module_docstring import check_module_docstring
from docpact.rules.doc.doc003_class_docstring import check_class_docstrings
from docpact.rules.doc.doc050_pydantic_field import check_pydantic_fields
from docpact.rules.fix.fix001_bare_noqa import check_bare_noqa
from docpact.rules.fix.fix002_no_reason import check_no_reason
from docpact.suppress import apply_suppressions, parse_suppressions
from docpact.tiers import assign_tier

if TYPE_CHECKING:
    from docpact.model.diagnostic import RuleResult


def _collect_py_files(paths: tuple[str, ...], config: Config) -> list[Path]:
    """Expand path arguments to a sorted list of .py files, honouring exclude patterns."""
    result: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for f in sorted(path.rglob("*.py")):
                if not file_is_excluded(f, config.exclude):
                    result.append(f)
        else:
            if not file_is_excluded(path, config.exclude):
                result.append(path)
    return result


def _run_checks(
    py_files: list[Path],
    config: Config,
) -> tuple[list[RuleResult], dict[Path, dict[int, frozenset[str]]]]:
    """Run all enabled rules over the given files and return results with suppression maps."""
    parser: GoogleParser | NumpyParser = (
        NumpyParser() if config.docstring_format == "numpy" else GoogleParser()
    )
    rules = all_rules()
    results: list[RuleResult] = []
    suppressions: dict[Path, dict[int, frozenset[str]]] = {}

    for file_path in py_files:
        source_text = file_path.read_text(errors="replace")
        file_suppressions = parse_suppressions(source_text, markers=config.suppress_comment)
        suppressions[file_path] = file_suppressions
        extra_ignores = file_ignores_for(file_path, config.per_file_ignores)

        # File-level rules: run once per file before function-level rules.
        if "FIX001" in rules:
            fix001_meta, _ = rules["FIX001"]
            if rule_is_enabled("FIX001", "FIX", config.select, config.ignore) and rule_is_enabled(
                "FIX001", "FIX", ("DOC", "MCP", "FIX"), extra_ignores
            ):
                severity = config.rule_severities.get("FIX001", fix001_meta.default_severity)
                cfg = RuleConfig(severity=severity, options={})
                results.extend(check_bare_noqa(source_text, file_suppressions, file_path, cfg))

        if "FIX002" in rules:
            fix002_meta, _ = rules["FIX002"]
            if rule_is_enabled("FIX002", "FIX", config.select, config.ignore) and rule_is_enabled(
                "FIX002", "FIX", ("DOC", "MCP", "FIX"), extra_ignores
            ):
                severity = config.rule_severities.get("FIX002", fix002_meta.default_severity)
                cfg = RuleConfig(severity=severity, options={})
                results.extend(
                    check_no_reason(
                        source_text,
                        file_suppressions,
                        file_path,
                        cfg,
                        markers=config.suppress_comment,
                    )
                )

        if "DOC002" in rules:
            doc002_meta, _ = rules["DOC002"]
            if rule_is_enabled("DOC002", "DOC", config.select, config.ignore) and rule_is_enabled(
                "DOC002", "DOC", ("DOC", "MCP", "FIX"), extra_ignores
            ):
                severity = config.rule_severities.get("DOC002", doc002_meta.default_severity)
                cfg = RuleConfig(severity=severity, options={})
                results.extend(check_module_docstring(source_text, file_path, cfg))

        if "DOC003" in rules:
            doc003_meta, _ = rules["DOC003"]
            if rule_is_enabled("DOC003", "DOC", config.select, config.ignore) and rule_is_enabled(
                "DOC003", "DOC", ("DOC", "MCP", "FIX"), extra_ignores
            ):
                severity = config.rule_severities.get("DOC003", doc003_meta.default_severity)
                cfg = RuleConfig(severity=severity, options={})
                results.extend(check_class_docstrings(source_text, file_path, cfg))

        if "DOC050" in rules:
            doc050_meta, _ = rules["DOC050"]
            if rule_is_enabled("DOC050", "DOC", config.select, config.ignore) and rule_is_enabled(
                "DOC050", "DOC", ("DOC", "MCP", "FIX"), extra_ignores
            ):
                severity = config.rule_severities.get("DOC050", doc050_meta.default_severity)
                cfg = RuleConfig(severity=severity, options={})
                results.extend(check_pydantic_fields(source_text, file_path, cfg))

        functions = extract_functions(file_path)
        for func in functions:
            doc = parser.parse(func.docstring_raw) if func.docstring_raw is not None else None
            tier = assign_tier(func, config.tier_overrides)
            config_options: dict[str, object] = {"tier": tier}
            for meta, rule_fn in rules.values():
                if meta.code in {"FIX001", "FIX002", "DOC002", "DOC003", "DOC050"}:
                    continue  # handled above as file-level rules
                if not rule_is_enabled(meta.code, meta.namespace, config.select, config.ignore):
                    continue
                if not rule_is_enabled(
                    meta.code, meta.namespace, ("DOC", "MCP", "FIX"), extra_ignores
                ):
                    continue
                severity = config.rule_severities.get(meta.code, meta.default_severity)
                cfg = RuleConfig(severity=severity, options=config_options)
                results.extend(rule_fn(func, doc, cfg))

    results.sort(key=lambda r: (str(r.location.file_path), r.location.line, r.location.column))
    return results, suppressions


@click.group()
@click.version_option()
def main() -> None:
    """docpact — docstring contract validator."""


@main.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--fix", "do_fix", is_flag=True, help="Apply safe fixes in-place.")
@click.option(
    "--unsafe-fixes",
    is_flag=True,
    help="Apply unsafe fixes in-place. Requires --fix.",
)
@click.option("--diff", is_flag=True, help="Show diff of fixes without writing files.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format.",
)
@click.option("--exit-zero", is_flag=True, help="Always exit 0, even when errors are found.")
@click.option(
    "--select",
    "cli_select",
    multiple=True,
    metavar="CODE",
    help="Rule codes or prefixes to enable (overrides config).",
)
@click.option(
    "--ignore",
    "cli_ignore",
    multiple=True,
    metavar="CODE",
    help="Rule codes or prefixes to disable (overrides config).",
)
def check(  # nodo: DOC012 -- click params; Args section would duplicate --help text
    paths: tuple[str, ...],
    do_fix: bool,
    unsafe_fixes: bool,
    diff: bool,
    output_format: str,
    exit_zero: bool,
    cli_select: tuple[str, ...],
    cli_ignore: tuple[str, ...],
) -> None:
    """Check docstrings against the configured schema."""
    config = load_config(Path.cwd())

    if cli_select:
        config = Config(
            schema=config.schema,
            docstring_format=config.docstring_format,
            select=cli_select,
            ignore=config.ignore,
            exclude=config.exclude,
            heuristics_default=config.heuristics_default,
            per_file_ignores=config.per_file_ignores,
            tier_overrides=config.tier_overrides,
            rule_severities=config.rule_severities,
        )
    if cli_ignore:
        config = Config(
            schema=config.schema,
            docstring_format=config.docstring_format,
            select=config.select,
            ignore=(*config.ignore, *cli_ignore),
            exclude=config.exclude,
            heuristics_default=config.heuristics_default,
            per_file_ignores=config.per_file_ignores,
            tier_overrides=config.tier_overrides,
            rule_severities=config.rule_severities,
        )

    py_files = _collect_py_files(paths, config)
    results, suppressions = _run_checks(py_files, config)

    apply_unsafe = unsafe_fixes and do_fix

    if diff:
        patch = diff_fixes(results, unsafe=apply_unsafe)
        if patch:
            click.echo(patch, nl=False)
        sys.exit(0)

    if do_fix:
        modified, conflicts = apply_fixes(results, unsafe=apply_unsafe)
        for conflict in conflicts:
            click.echo(f"warning: {conflict}", err=True)
        # Re-run checks on modified files so reported results reflect post-fix state.
        if modified:
            results, suppressions = _run_checks(py_files, config)

    # Apply inline suppressions before output and exit-code evaluation.
    visible = apply_suppressions(results, suppressions)

    cwd = Path.cwd()
    if output_format == "text":
        text = format_text(visible, cwd=cwd)
        if text:
            click.echo(text)
        summary = format_summary(visible)
        if summary:
            click.echo(summary)
    elif output_format == "json":
        click.echo(format_json(visible, cwd=cwd))

    if visible and not exit_zero:
        sys.exit(1)


@main.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--diff", is_flag=True, help="Show diff without writing files.")
def generate(  # nodo: DOC012 -- click params; Args section would duplicate --help text
    paths: tuple[str, ...], diff: bool
) -> None:
    """Generate stub docstrings for undocumented functions."""
    config = load_config(Path.cwd())
    # Only DOC001 produces stubs; no other rule should drive generation.
    stub_config = Config(
        schema=config.schema,
        docstring_format=config.docstring_format,
        select=("DOC001",),
        ignore=(),
        exclude=config.exclude,
        heuristics_default=config.heuristics_default,
        per_file_ignores=config.per_file_ignores,
        tier_overrides=config.tier_overrides,
        rule_severities=config.rule_severities,
    )
    py_files = _collect_py_files(paths, stub_config)
    results, suppressions = _run_checks(py_files, stub_config)
    visible = apply_suppressions(results, suppressions)

    if diff:
        patch = diff_fixes(visible)
        if patch:
            click.echo(patch, nl=False)
        sys.exit(0)

    modified, conflicts = apply_fixes(visible)
    for conflict in conflicts:
        click.echo(f"warning: {conflict}", err=True)

    if modified:
        cwd = Path.cwd()
        for path in sorted(modified):
            try:
                rel = path.relative_to(cwd)
            except ValueError:
                rel = path
            click.echo(f"Generated: {rel}")
        click.echo(f"Generated {sum(1 for r in visible if r.fix is not None)} stub docstring(s).")
    else:
        click.echo("No undocumented functions found.")


# Per-tier schema: (title, required, recommended, optional)
_TIER_SCHEMA: dict[int, tuple[str, list[str], list[str], list[str]]] = {
    1: (
        "Internal functions",
        ["Summary"],
        ["Args (when non-trivial)", "Returns (when non-trivial)"],
        ["Raises", "Notes", "Examples"],
    ),
    2: (
        "Package-public functions and methods",
        ["Summary", "Args (when params present)", "Returns (if non-None)"],
        ["Raises", "Constraints", "Stability"],
        ["Mutates", "Notes", "See Also", "Examples", "Alternatives", "References"],
    ),
    3: (
        "MCP-exposed functions",
        [
            "Summary",
            "Args",
            "Returns",
            "Raises",
            "Constraints",
            "Stability",
            "MCP (or decorator description=)",
        ],
        ["Mutates", "See Also"],
        ["Notes", "Alternatives", "References", "Examples"],
    ),
    4: (
        "FastAPI routes via FastMCP.from_fastapi()",
        [
            "Summary",
            "Args",
            "Returns",
            "Raises",
            "Constraints",
            "Stability",
            "MCP (or decorator description=)",
        ],
        ["Mutates", "See Also"],
        ["Notes", "Alternatives", "References", "Examples"],
    ),
}


def _wrap_items(items: list[str], indent: int, width: int = 78) -> str:
    """Format a comma-separated list with line wrapping at width."""
    prefix = " " * indent
    line = ", ".join(items)
    if len(prefix) + len(line) <= width:
        return prefix + line
    # Wrap long lists.
    lines: list[str] = []
    current = prefix
    continuation = " " * indent
    for i, item in enumerate(items):
        sep = ", " if i < len(items) - 1 else ""
        candidate = current + item + sep
        if lines and len(candidate) > width:
            lines.append(current.rstrip(", "))
            current = continuation + item + sep
        else:
            current = candidate
    lines.append(current)
    return "\n".join(lines)


@main.command(name="show-schema")
@click.option("--tier", type=click.IntRange(1, 4), required=True)
def show_schema(  # nodo: DOC012 -- click params; Args section would duplicate --help text
    tier: int,
) -> None:
    """Print the schema requirements for a given tier."""
    title, required, recommended, optional = _TIER_SCHEMA[tier]
    click.echo(f"\nTier {tier} — {title}\n")
    label_width = 13  # "Recommended: " is the widest label
    click.echo(f"  {'Required:':<{label_width}}{_wrap_items(required, label_width + 2).lstrip()}")
    click.echo(
        f"  {'Recommended:':<{label_width}}{_wrap_items(recommended, label_width + 2).lstrip()}"
    )
    click.echo(f"  {'Optional:':<{label_width}}{_wrap_items(optional, label_width + 2).lstrip()}")
    click.echo()


@main.command(name="list-rules")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
)
def list_rules(  # nodo: DOC012 -- click params; Args section would duplicate --help text
    output_format: str,
) -> None:
    """List all defined rules with their default severity."""
    import json as _json

    rules = sorted(all_rules().items(), key=lambda kv: kv[0])

    if output_format == "json":
        data = [
            {
                "code": meta.code,
                "namespace": meta.namespace,
                "severity": meta.default_severity.value,
                "fixable": meta.fixable,
                "unsafe_fixable": meta.unsafe_fixable,
                "summary": meta.summary,
            }
            for _, (meta, _) in rules
        ]
        click.echo(_json.dumps(data, indent=2))
        return

    # Text: aligned table.
    header = f"{'Code':<8}  {'Severity':<8}  {'Fix':<5}  Summary"
    sep = f"{'─' * 8}  {'─' * 8}  {'─' * 5}  {'─' * 48}"
    click.echo(header)
    click.echo(sep)
    for _, (meta, _) in rules:
        fix_marker = "[*] " if meta.fixable else "    "
        fix_marker += "[!]" if meta.unsafe_fixable else "   "
        click.echo(
            f"{meta.code:<8}  {meta.default_severity.value:<8}  {fix_marker}  {meta.summary}"
        )


if __name__ == "__main__":
    main()

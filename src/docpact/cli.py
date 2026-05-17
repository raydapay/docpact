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
import docpact.rules.doc.doc007_param_mismatch  # noqa: F401
from docpact.output import format_summary, format_text
from docpact.parser.docstring import GoogleParser
from docpact.parser.source import extract_functions
from docpact.rules._registry import RuleConfig, all_rules
from docpact.tiers import assign_tier

if TYPE_CHECKING:
    from docpact.model.diagnostic import RuleResult


def _collect_py_files(paths: tuple[str, ...]) -> list[Path]:
    result: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            result.extend(sorted(path.rglob("*.py")))
        else:
            result.append(path)
    return result


def _run_checks(py_files: list[Path]) -> list[RuleResult]:
    parser = GoogleParser()
    rules = all_rules()
    results: list[RuleResult] = []

    for file_path in py_files:
        functions = extract_functions(file_path)
        for func in functions:
            doc = parser.parse(func.docstring_raw) if func.docstring_raw is not None else None
            tier = assign_tier(func)
            config_options: dict[str, object] = {"tier": tier}
            for meta, rule_fn in rules.values():
                cfg = RuleConfig(severity=meta.default_severity, options=config_options)
                results.extend(rule_fn(func, doc, cfg))

    results.sort(key=lambda r: (str(r.location.file_path), r.location.line, r.location.column))
    return results


@click.group()
@click.version_option()
def main() -> None:
    """docpact — docstring contract validator."""


@main.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--fix", is_flag=True, help="Apply safe fixes in-place.")
@click.option("--unsafe-fixes", is_flag=True, help="Apply unsafe fixes. Requires --fix.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format.",
)
@click.option("--exit-zero", is_flag=True, help="Always exit 0, even when errors are found.")
def check(
    paths: tuple[str, ...],
    fix: bool,
    unsafe_fixes: bool,
    output_format: str,
    exit_zero: bool,
) -> None:
    """Check docstrings against the configured schema."""
    py_files = _collect_py_files(paths)
    results = _run_checks(py_files)

    cwd = Path.cwd()
    if output_format == "text":
        text = format_text(results, cwd=cwd)
        if text:
            click.echo(text)
        summary = format_summary(results)
        if summary:
            click.echo(summary)

    if results and not exit_zero:
        sys.exit(1)


@main.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
def generate(paths: tuple[str, ...]) -> None:
    """Generate stub docstrings for undocumented functions."""
    raise NotImplementedError("generate command not yet implemented")


@main.command(name="show-schema")
@click.option("--tier", type=click.IntRange(1, 4), required=True)
def show_schema(tier: int) -> None:
    """Print the schema requirements for a given tier."""
    raise NotImplementedError("show-schema command not yet implemented")


@main.command(name="list-rules")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
)
def list_rules(output_format: str) -> None:
    """List all defined rules with their default severity."""
    raise NotImplementedError("list-rules command not yet implemented")


if __name__ == "__main__":
    main()

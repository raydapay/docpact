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
from docpact.config import Config, file_ignores_for, file_is_excluded, load_config, rule_is_enabled
from docpact.fix import apply_fixes, diff_fixes
from docpact.output import format_summary, format_text
from docpact.parser.docstring import GoogleParser
from docpact.parser.source import extract_functions
from docpact.rules._registry import RuleConfig, all_rules
from docpact.tiers import assign_tier

if TYPE_CHECKING:
    from docpact.model.diagnostic import RuleResult


def _collect_py_files(paths: tuple[str, ...], config: Config) -> list[Path]:
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


def _run_checks(py_files: list[Path], config: Config) -> list[RuleResult]:
    parser = GoogleParser()
    rules = all_rules()
    results: list[RuleResult] = []

    for file_path in py_files:
        extra_ignores = file_ignores_for(file_path, config.per_file_ignores)
        functions = extract_functions(file_path)
        for func in functions:
            doc = parser.parse(func.docstring_raw) if func.docstring_raw is not None else None
            tier = assign_tier(func, config.tier_overrides)
            config_options: dict[str, object] = {"tier": tier}
            for meta, rule_fn in rules.values():
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
    return results


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
def check(
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
    results = _run_checks(py_files, config)

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
            results = _run_checks(py_files, config)

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

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

import dataclasses
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click

from docpact.baseline import add_suppressions as baseline_add
from docpact.baseline import diff_suppressions as baseline_diff
from docpact.config import (
    Config,
    ConfigError,
    ConfigResult,
    file_ignores_for,
    file_is_excluded,
    file_tier_override_for,
    load_config,
    load_config_from,
    rule_is_enabled,
    rule_is_file_ignored,
)
from docpact.fix import apply_fixes, diff_fixes
from docpact.model.diagnostic import Severity
from docpact.output import (
    format_github,
    format_json,
    format_sarif,
    format_statistics,
    format_summary,
    format_text,
)
from docpact.parser.docstring import GoogleParser, NumpyParser
from docpact.parser.source import extract_functions, parse_all_names, parse_tier_pragma
from docpact.rules import load_builtin_rules
from docpact.rules._registry import RuleConfig, all_rules
from docpact.rules.doc.doc002_module_docstring import check_module_docstring
from docpact.rules.doc.doc003_class_docstring import check_class_docstrings
from docpact.rules.doc.doc050_pydantic_field import check_pydantic_fields
from docpact.rules.fix.fix001_bare_noqa import check_bare_noqa
from docpact.rules.fix.fix002_no_reason import check_no_reason
from docpact.rules.fix.fix003_stale_suppression import check_stale_suppressions
from docpact.suppress import apply_suppressions, parse_suppressions
from docpact.tiers import assign_tier

load_builtin_rules()

if TYPE_CHECKING:
    from docpact.model.diagnostic import RuleResult


def _get_changed_py_files(ref: str, cwd: Path) -> set[Path]:
    """Return resolved absolute paths of .py files changed relative to a git ref."""
    root_result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if root_result.returncode != 0:
        raise click.UsageError(
            f"--changed-only requires a git repository: {root_result.stderr.strip()}"
        )
    git_root = Path(root_result.stdout.strip())

    diff_result = subprocess.run(
        ["git", "diff", "--name-only", ref, "--", "*.py"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if diff_result.returncode != 0:
        raise click.UsageError(
            f"--changed-only: invalid git ref {ref!r}: {diff_result.stderr.strip()}"
        )

    changed: set[Path] = set()
    for line in diff_result.stdout.splitlines():
        stripped = line.strip()
        if stripped:
            changed.add((git_root / stripped).resolve())
    return changed


def _collect_py_files(paths: tuple[str, ...], config: Config, root: Path) -> list[Path]:
    """Expand path arguments to a sorted list of .py files, honouring exclude patterns."""
    result: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for f in sorted(path.rglob("*.py")):
                if not file_is_excluded(f, config.exclude, root):
                    result.append(f)
        else:
            if not file_is_excluded(path, config.exclude, root):
                result.append(path)
    return result


def _filter_gitignored(files: list[Path], cwd: Path) -> list[Path]:
    """Remove files that git considers ignored. No-op outside git repos."""
    if not files:
        return files
    try:
        result = subprocess.run(
            ["git", "check-ignore", "--stdin"],
            input="\n".join(str(f) for f in files),
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        # 0 = some ignored, 1 = none ignored, other = not a git repo or error
        if result.returncode not in (0, 1):
            return files
        ignored = {Path(s.strip()).resolve() for s in result.stdout.splitlines() if s.strip()}
        return [f for f in files if f.resolve() not in ignored]
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return files


def _expand_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    """Split comma-separated code tokens and flatten into a single tuple.

    Allows ``--select DOC021,DOC003`` as shorthand for
    ``--select DOC021 --select DOC003``, matching ruff/ty behaviour.
    """
    return tuple(c.strip() for raw in codes for c in raw.split(",") if c.strip())


_FILE_LEVEL_CODES: frozenset[str] = frozenset(
    {"FIX001", "FIX002", "FIX003", "DOC002", "DOC003", "DOC050"}
)


def _run_checks(
    py_files: list[Path],
    config: Config,
    root: Path,
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
        extra_ignores = file_ignores_for(file_path, config.per_file_ignores, root)

        # Accumulate per-file so FIX003 can inspect the full violation set.
        file_results: list[RuleResult] = []

        # File-level rules: run once per file before function-level rules.
        for code, namespace in (
            ("FIX001", "FIX"),
            ("FIX002", "FIX"),
            ("DOC002", "DOC"),
            ("DOC003", "DOC"),
            ("DOC050", "DOC"),
        ):
            if code not in rules:
                continue
            meta, _ = rules[code]
            if not rule_is_enabled(code, namespace, config.select, config.ignore):
                continue
            if rule_is_file_ignored(code, namespace, extra_ignores):
                continue
            severity = config.rule_severities.get(code, meta.default_severity)
            if severity == Severity.OFF:
                continue
            cfg = RuleConfig(severity=severity, options={})
            match code:
                case "FIX001":
                    file_results.extend(
                        check_bare_noqa(source_text, file_suppressions, file_path, cfg)
                    )
                case "FIX002":
                    file_results.extend(
                        check_no_reason(
                            source_text,
                            file_suppressions,
                            file_path,
                            cfg,
                            markers=config.suppress_comment,
                        )
                    )
                case "DOC002":
                    file_results.extend(check_module_docstring(source_text, file_path, cfg))
                case "DOC003":
                    # per-file-tier = 1 silences DOC003 for classes in that file,
                    # consistent with how tier 1 silences function-level rules.
                    if file_tier_override_for(file_path, config.tier_overrides, root) != 1:
                        file_results.extend(check_class_docstrings(source_text, file_path, cfg))
                case "DOC050":
                    file_results.extend(check_pydantic_fields(source_text, file_path, cfg))

        all_names = parse_all_names(source_text)
        source_lines = source_text.splitlines()
        functions = extract_functions(file_path)
        for func in functions:
            doc = parser.parse(func.docstring_raw) if func.docstring_raw is not None else None
            tier = assign_tier(func, config.tier_overrides, all_names=all_names, root=root)
            if config.allow_pragma:
                line_text = (
                    source_lines[func.line - 1] if 0 < func.line <= len(source_lines) else ""
                )
                pragma_tier = parse_tier_pragma(line_text)
                if pragma_tier is not None:
                    tier = pragma_tier
            config_options: dict[str, object] = {"tier": tier}
            for meta, rule_fn in rules.values():
                if meta.code in _FILE_LEVEL_CODES:
                    continue  # handled as file-level rules (pre- or post-pass)
                if not rule_is_enabled(meta.code, meta.namespace, config.select, config.ignore):
                    continue
                if rule_is_file_ignored(meta.code, meta.namespace, extra_ignores):
                    continue
                severity = config.rule_severities.get(meta.code, meta.default_severity)
                if severity == Severity.OFF:
                    continue
                cfg = RuleConfig(severity=severity, options=config_options)
                file_results.extend(rule_fn(func, doc, cfg))

        # FIX003 post-pass: needs the complete violation set for this file.
        if (
            "FIX003" in rules
            and rule_is_enabled("FIX003", "FIX", config.select, config.ignore)
            and not rule_is_file_ignored("FIX003", "FIX", extra_ignores)
        ):
            meta, _ = rules["FIX003"]
            severity = config.rule_severities.get("FIX003", meta.default_severity)
            if severity != Severity.OFF:
                cfg = RuleConfig(severity=severity, options={})
                file_results.extend(
                    check_stale_suppressions(
                        source_text, file_suppressions, file_results, file_path, cfg
                    )
                )

        results.extend(file_results)

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
    type=click.Choice(["text", "json", "sarif", "github"]),
    default="text",
    help="Output format.",
)
@click.option("--exit-zero", is_flag=True, help="Always exit 0, even when errors are found.")
@click.option(
    "--select",
    "cli_select",
    multiple=True,
    metavar="CODE",
    help="Rule codes or prefixes to enable (replaces config select).",
)
@click.option(
    "--ignore",
    "cli_ignore",
    multiple=True,
    metavar="CODE",
    help="Rule codes or prefixes to disable (extends config ignore).",
)
@click.option(
    "--extend-select",
    "cli_extend_select",
    multiple=True,
    metavar="CODE",
    help="Add rule codes or prefixes to the config's select set.",
)
@click.option(
    "--extend-ignore",
    "cli_extend_ignore",
    multiple=True,
    metavar="CODE",
    help="Add rule codes or prefixes to the config's ignore set.",
)
@click.option(
    "--config",
    "config_path",
    default=None,
    metavar="PATH",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Explicit path to pyproject.toml or docpact.toml; bypasses discovery.",
)
@click.option(
    "--no-config", "no_config", is_flag=True, help="Ignore all configuration files; use defaults."
)
@click.option(
    "-q", "--quiet", is_flag=True, help="Suppress the summary line; show diagnostics only."
)
@click.option(
    "--statistics", is_flag=True, help="Print per-rule violation counts after diagnostics."
)
@click.option(
    "--color",
    "color_mode",
    type=click.Choice(["auto", "always", "never"]),
    default="auto",
    show_default=True,
    help="Control ANSI color in text output.",
)
@click.option(
    "--output-file",
    "output_file",
    default=None,
    metavar="PATH",
    help="Write output to PATH instead of stdout. Disables color.",
)
@click.option(
    "--no-respect-gitignore",
    "no_respect_gitignore",
    is_flag=True,
    help="Check files even if they are listed in .gitignore.",
)
@click.option(
    "--add-suppression",
    "add_suppression",
    is_flag=True,
    help="Add # nodo: suppression comments for all current violations (baselining).",
)
@click.option(
    "--suppression-reason",
    "suppression_reason",
    default="baseline",
    show_default=True,
    metavar="TEXT",
    help="Reason text appended to generated suppression comments.",
)
@click.option(
    "--changed-only",
    "changed_only",
    metavar="REF",
    default=None,
    help="Restrict checks to .py files changed relative to REF (e.g. main, HEAD~1).",
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
    cli_extend_select: tuple[str, ...],
    cli_extend_ignore: tuple[str, ...],
    config_path: Path | None,
    no_config: bool,
    quiet: bool,
    statistics: bool,
    color_mode: str,
    output_file: str | None,
    no_respect_gitignore: bool,
    add_suppression: bool,
    suppression_reason: str,
    changed_only: str | None,
) -> None:
    """Check docstrings against the configured schema."""
    if unsafe_fixes and not do_fix:
        raise click.UsageError("--unsafe-fixes requires --fix")

    try:
        if no_config:
            cfg_result = ConfigResult(config=Config(), root=Path.cwd())
        elif config_path is not None:
            cfg_result = load_config_from(config_path)
        else:
            cfg_result = load_config(Path.cwd())
    except ConfigError as exc:
        raise click.UsageError(str(exc)) from exc
    config = cfg_result.config
    config_root = cfg_result.root

    cli_select = _expand_codes(cli_select)
    cli_ignore = _expand_codes(cli_ignore)
    cli_extend_select = _expand_codes(cli_extend_select)
    cli_extend_ignore = _expand_codes(cli_extend_ignore)

    if cli_select:
        config = dataclasses.replace(config, select=cli_select)
    if cli_ignore:
        config = dataclasses.replace(config, ignore=(*config.ignore, *cli_ignore))
    if cli_extend_select:
        config = dataclasses.replace(config, select=(*config.select, *cli_extend_select))
    if cli_extend_ignore:
        config = dataclasses.replace(config, ignore=(*config.ignore, *cli_extend_ignore))

    py_files = _collect_py_files(paths, config, config_root)
    if config.respect_gitignore and not no_respect_gitignore:
        py_files = _filter_gitignored(py_files, Path.cwd())
    if changed_only is not None:
        changed_set = _get_changed_py_files(changed_only, Path.cwd())
        py_files = [f for f in py_files if f.resolve() in changed_set]
    results, suppressions = _run_checks(py_files, config, config_root)

    apply_unsafe = unsafe_fixes and do_fix

    # --diff without --add-suppression shows fix preview and exits.
    if diff and not add_suppression:
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
            results, suppressions = _run_checks(py_files, config, config_root)

    # Apply inline suppressions before output and exit-code evaluation.
    visible = apply_suppressions(results, suppressions)

    if add_suppression:
        if diff:
            patch = baseline_diff(
                visible, reason=suppression_reason, markers=config.suppress_comment
            )
            if patch:
                click.echo(patch, nl=False)
            sys.exit(0)
        counts = baseline_add(visible, reason=suppression_reason, markers=config.suppress_comment)
        total = sum(counts.values())
        if total:
            click.echo(
                f"Added suppression comments to {total} location(s) across {len(counts)} file(s)."
            )
        else:
            click.echo("No violations to suppress.")
        sys.exit(0)

    cwd = Path.cwd()
    # Color is disabled when writing to a file (ANSI codes are useless in files).
    use_color = output_file is None and (
        color_mode == "always" or (color_mode == "auto" and sys.stdout.isatty())
    )

    if output_format == "text":
        parts: list[str] = []
        text = format_text(visible, cwd=cwd, color=use_color)
        if text:
            parts.append(text)
        if statistics:
            stats = format_statistics(visible)
            if stats:
                parts.append(stats)
        if not quiet:
            summary = format_summary(visible)
            if summary:
                parts.append(summary)
        output_str = "\n".join(parts)
    elif output_format == "json":
        output_str = format_json(visible, cwd=cwd)
    elif output_format == "sarif":
        output_str = format_sarif(visible, cwd=cwd)
    else:  # github
        output_str = format_github(visible, cwd=cwd)

    if output_file:
        Path(output_file).write_text(output_str + "\n" if output_str else "")
    elif output_str:
        click.echo(output_str)

    has_errors = any(r.severity == Severity.ERROR for r in visible)
    if has_errors and not exit_zero:
        sys.exit(1)


@main.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--diff", is_flag=True, help="Show diff without writing files.")
@click.option(
    "--no-config", "no_config", is_flag=True, help="Ignore all configuration files; use defaults."
)
def generate(  # nodo: DOC012 -- click params; Args section would duplicate --help text
    paths: tuple[str, ...], diff: bool, no_config: bool
) -> None:
    """Generate stub docstrings for undocumented functions."""
    try:
        cfg_result = (
            ConfigResult(config=Config(), root=Path.cwd()) if no_config else load_config(Path.cwd())
        )
    except ConfigError as exc:
        raise click.UsageError(str(exc)) from exc
    config = cfg_result.config
    config_root = cfg_result.root
    # Only DOC001 produces stubs; no other rule should drive generation.
    stub_config = dataclasses.replace(config, select=("DOC001",), ignore=())
    py_files = _collect_py_files(paths, stub_config, config_root)
    if stub_config.respect_gitignore:
        py_files = _filter_gitignored(py_files, Path.cwd())
    results, suppressions = _run_checks(py_files, stub_config, config_root)
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

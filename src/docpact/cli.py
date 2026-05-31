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
import functools
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
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
    file_matches_any,
    file_tier_override_for,
    load_config,
    load_config_from,
    rule_is_enabled,
    rule_is_file_ignored,
)
from docpact.crossfile import CrossfileResult, resolve_crossfile
from docpact.fix import apply_fixes, diff_fixes
from docpact.lsp import LSPError
from docpact.model.diagnostic import Severity
from docpact.output import (
    format_github,
    format_json,
    format_sarif,
    format_statistics,
    format_summary,
    format_suppress_hint,
    format_text,
)
from docpact.parser.docstring import GoogleParser, NumpyParser
from docpact.parser.registry import extract_tool_registry
from docpact.parser.source import extract_functions, parse_all_names, parse_tier_pragma
from docpact.rules import load_builtin_rules
from docpact.rules._registry import RuleConfig, RuleFn, RuleMetadata, all_rules
from docpact.rules.doc.doc002_module_docstring import check_module_docstring
from docpact.rules.doc.doc003_class_docstring import check_class_docstrings
from docpact.rules.doc.doc050_pydantic_field import check_pydantic_fields
from docpact.rules.fix.fix001_bare_noqa import check_bare_noqa
from docpact.rules.fix.fix002_no_reason import check_no_reason
from docpact.rules.fix.fix003_stale_suppression import check_stale_suppressions
from docpact.rules.fix.fix004_misplaced_suppression import check_misplaced_suppressions
from docpact.rules.parse.parse001_syntax_error import check_syntax_error as check_parse_syntax_error
from docpact.rules.reg.reg001_schema_phantom_param import check_registry_phantom_params
from docpact.rules.reg.reg002_unmatched_entry import check_unmatched_entries
from docpact.semantic.analyzer import SYSTEM as _SEM_SYSTEM
from docpact.semantic.analyzer import analyze as _sem_analyze
from docpact.semantic.analyzer import build_batches as _sem_build_batches
from docpact.semantic.analyzer import user_prompt as _sem_user_prompt
from docpact.semantic.backend import SemanticError, make_backend
from docpact.suppress import apply_suppressions, parse_suppressions
from docpact.tiers import assign_tier

load_builtin_rules()

if TYPE_CHECKING:
    from docpact.model.diagnostic import RuleResult
    from docpact.model.function_info import FunctionInfo
    from docpact.model.tool_registry import ToolRegistryEntry


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
            input="\n".join(f.as_posix() for f in files),
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


# Codes handled outside the per-function loop in _run_checks.
# FIX001/FIX002/FIX004/DOC002/DOC003/DOC050 run as a pre-pass (once per file);
# FIX003 runs as a post-pass (needs the full file violation set);
# REG001/REG002 run as a post-pass (need the file's functions and registry);
# PARSE001 is emitted on SyntaxError before the function loop runs.
# Invariant: every code here must appear in _run_checks's match block OR the
# FIX003/REG post-pass blocks. The test_file_level_codes_invariant test enforces this.
_FILE_LEVEL_CODES: frozenset[str] = frozenset(
    {
        "FIX001",
        "FIX002",
        "FIX003",
        "FIX004",
        "DOC002",
        "DOC003",
        "DOC050",
        "PARSE001",
        "REG001",
        "REG002",
    }
)


def _run_file_level_rules(
    file_path: Path,
    source_text: str,
    file_suppressions: dict[int, frozenset[str]],
    extra_ignores: frozenset[str],
    config: Config,
    root: Path,
    rules: dict[str, tuple[RuleMetadata, RuleFn]],
) -> list[RuleResult]:
    """Run pre-pass file-level rules (FIX001/002/004, DOC002/003/050) once per file."""
    file_results: list[RuleResult] = []
    for code, namespace in (
        ("FIX001", "FIX"),
        ("FIX002", "FIX"),
        ("FIX004", "FIX"),
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
                file_results.extend(check_bare_noqa(source_text, file_suppressions, file_path, cfg))
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
            case "FIX004":
                file_results.extend(
                    check_misplaced_suppressions(source_text, file_suppressions, file_path, cfg)
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
    return file_results


def _run_function_level_rules(
    file_path: Path,
    functions: list[FunctionInfo],
    source_text: str,
    parser: GoogleParser | NumpyParser,
    all_names: frozenset[str] | None,
    registered_tool_names: frozenset[str] | None,
    extra_ignores: frozenset[str],
    config: Config,
    root: Path,
    rules: dict[str, tuple[RuleMetadata, RuleFn]],
) -> list[RuleResult]:
    """Run function-level rules for every function definition in one file."""
    source_lines = source_text.splitlines()
    file_results: list[RuleResult] = []
    for func in functions:
        doc = parser.parse(func.docstring_raw) if func.docstring_raw is not None else None
        tier = assign_tier(
            func,
            config.tier_overrides,
            all_names=all_names,
            registered_tool_names=registered_tool_names,
            root=root,
        )
        if config.allow_pragma:
            line_text = source_lines[func.line - 1] if 0 < func.line <= len(source_lines) else ""
            pragma_tier = parse_tier_pragma(line_text)
            if pragma_tier is not None:
                tier = pragma_tier
        config_options: dict[str, object] = {
            "tier": tier,
            "require_examples_min_tier": config.require_examples_min_tier,
        }
        for meta, rule_fn in rules.values():
            if meta.code in _FILE_LEVEL_CODES:
                continue  # handled as file-level or post-pass rules
            if not rule_is_enabled(meta.code, meta.namespace, config.select, config.ignore):
                continue
            if rule_is_file_ignored(meta.code, meta.namespace, extra_ignores):
                continue
            severity = config.rule_severities.get(meta.code, meta.default_severity)
            if severity == Severity.OFF:
                continue
            cfg = RuleConfig(severity=severity, options=config_options)
            file_results.extend(rule_fn(func, doc, cfg))
    return file_results


def _registry_is_active(config: Config, extra_ignores: frozenset[str]) -> bool:
    """Return True if REG-namespace detection should run for a file.

    The REG namespace is opt-in: a project enables registry detection (the
    REG rules and the Tier 3 floor) by adding ``REG`` to ``select``. File-level
    ``per-file-ignores`` of the whole namespace also disables it.
    """
    return rule_is_enabled("REG001", "REG", config.select, config.ignore) and not (
        rule_is_file_ignored("REG001", "REG", extra_ignores)
        and rule_is_file_ignored("REG002", "REG", extra_ignores)
    )


def _registry_floor_names(
    entries: list[ToolRegistryEntry],
    file_path: Path,
    config: Config,
    root: Path,
) -> frozenset[str] | None:
    """Return the registered names that should receive the Tier 3 floor, or None.

    None when the floor is disabled for this file — either ``assign_tier = false``
    project-wide or the file matches a ``no_tier_floor`` glob (ADR-005).
    """
    if not entries or not config.registry.assign_tier:
        return None
    if file_matches_any(file_path, config.registry.no_tier_floor, root):
        return None
    return frozenset(e.name for e in entries)


def _run_registry_rules(
    functions: list[FunctionInfo],
    entries: list[ToolRegistryEntry],
    file_path: Path,
    extra_ignores: frozenset[str],
    config: Config,
    rules: dict[str, tuple[RuleMetadata, RuleFn]],
) -> list[RuleResult]:
    """Run REG001/REG002 over a file's functions and extracted registry entries."""
    file_results: list[RuleResult] = []
    for code, check_fn in (
        ("REG001", check_registry_phantom_params),
        ("REG002", check_unmatched_entries),
    ):
        if code not in rules:
            continue
        if not rule_is_enabled(code, "REG", config.select, config.ignore):
            continue
        if rule_is_file_ignored(code, "REG", extra_ignores):
            continue
        meta, _ = rules[code]
        severity = config.rule_severities.get(code, meta.default_severity)
        if severity == Severity.OFF:
            continue
        cfg = RuleConfig(severity=severity, options={})
        file_results.extend(check_fn(functions, entries, file_path, cfg))
    return file_results


def _check_one_file(
    file_path: Path,
    config: Config,
    root: Path,
    crossfile_floor: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[list[RuleResult], dict[int, frozenset[str]]]:
    """Run all enabled rules over a single file.

    Self-contained so it can run unchanged in the main process or in a worker
    process: it derives the rule registry and parser itself rather than taking
    them as arguments, and all of its inputs are picklable.

    Args:
        file_path: The .py file to analyze.
        config: Resolved configuration.
        root: Project root, for anchoring per-file glob patterns.
        crossfile_floor: ``(resolved-file, function-name)`` pairs that an
            imported handler is registered under (ADR-010). Names matching this
            file augment the same-file Tier-3 floor, so a function registered
            as a tool in another module is held to the agent-facing bar here.

    Returns:
        A pair of (diagnostics for this file, suppression map for this file).
        Diagnostics are unsorted; the caller sorts the merged set.
    """
    rules = all_rules()
    parser: GoogleParser | NumpyParser = (
        NumpyParser() if config.docstring_format == "numpy" else GoogleParser()
    )

    source_text = file_path.read_text(encoding="utf-8", errors="replace")
    file_suppressions = parse_suppressions(source_text, markers=config.suppress_comment)
    extra_ignores = file_ignores_for(file_path, config.per_file_ignores, root)

    # Accumulate per-file so FIX003 can inspect the full violation set.
    file_results = _run_file_level_rules(
        file_path, source_text, file_suppressions, extra_ignores, config, root, rules
    )

    all_names = parse_all_names(source_text)

    try:
        functions = extract_functions(file_path)
    except SyntaxError as exc:
        if (
            "PARSE001" in rules
            and rule_is_enabled("PARSE001", "PARSE", config.select, config.ignore)
            and not rule_is_file_ignored("PARSE001", "PARSE", extra_ignores)
        ):
            meta, _ = rules["PARSE001"]
            severity = config.rule_severities.get("PARSE001", meta.default_severity)
            if severity != Severity.OFF:
                cfg = RuleConfig(severity=severity, options={})
                file_results.append(check_parse_syntax_error(exc, file_path, cfg))
        return file_results, file_suppressions

    # Tool-registry extraction (ADR-005): opt-in via the REG namespace.
    # Feeds both the Tier 3 floor below and the REG post-pass.
    registry_entries: list[ToolRegistryEntry] = []
    floor_names: frozenset[str] | None = None
    if _registry_is_active(config, extra_ignores):
        registry_entries = extract_tool_registry(
            source_text,
            tool_classes=config.registry.tool_definition_class,
            name_field=config.registry.name_field,
            description_field=config.registry.description_field,
            parameters_field=config.registry.parameters_field,
            input_model_field=config.registry.input_model_field,
            handler_field=config.registry.handler_field,
            description_parser=parser,
        )
        floor_names = _registry_floor_names(registry_entries, file_path, config, root)

    # Cross-file Tier-3 floor (ADR-010): handlers registered in another module
    # and resolved to this file are held to the agent-facing bar here too.
    crossfile_names = frozenset(
        name for (f, name) in crossfile_floor if f == file_path.resolve().as_posix()
    )
    if crossfile_names:
        floor_names = (floor_names or frozenset()) | crossfile_names

    file_results.extend(
        _run_function_level_rules(
            file_path,
            functions,
            source_text,
            parser,
            all_names,
            floor_names,
            extra_ignores,
            config,
            root,
            rules,
        )
    )

    # REG post-pass: needs the file's functions and its registry entries.
    if registry_entries:
        file_results.extend(
            _run_registry_rules(
                functions, registry_entries, file_path, extra_ignores, config, rules
            )
        )

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

    return file_results, file_suppressions


def _resolve_jobs(jobs: int) -> int:
    """Resolve a configured jobs value to a concrete worker count (>= 1)."""
    if jobs == 0:  # auto
        return os.cpu_count() or 1
    return max(1, jobs)


def _map_files(
    py_files: list[Path],
    config: Config,
    root: Path,
    crossfile_floor: frozenset[tuple[str, str]] = frozenset(),
) -> list[tuple[list[RuleResult], dict[int, frozenset[str]]]]:
    """Analyze every file, serially or across worker processes per config.jobs.

    Executor choice is isolated here so a future switch to ThreadPoolExecutor
    (under free-threaded Python) is a one-line change — see ADR-006 item 5.
    """
    workers = _resolve_jobs(config.jobs)
    if workers == 1 or len(py_files) <= 1:
        return [_check_one_file(f, config, root, crossfile_floor) for f in py_files]

    # ProcessPoolExecutor: CPU-bound parsing needs real parallelism, which the
    # GIL denies to threads. map() preserves input order; results are sorted
    # again below, so completion order never affects output (determinism holds).
    worker = functools.partial(
        _check_one_file, config=config, root=root, crossfile_floor=crossfile_floor
    )
    with ProcessPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(worker, py_files))


def _run_checks(
    py_files: list[Path],
    config: Config,
    root: Path,
    crossfile_floor: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[list[RuleResult], dict[Path, dict[int, frozenset[str]]]]:
    """Run all enabled rules over the given files and return results with suppression maps."""
    results: list[RuleResult] = []
    suppressions: dict[Path, dict[int, frozenset[str]]] = {}

    for file_path, (file_results, file_suppressions) in zip(
        py_files, _map_files(py_files, config, root, crossfile_floor), strict=True
    ):
        suppressions[file_path] = file_suppressions
        results.extend(file_results)

    results.sort(key=lambda r: (str(r.location.file_path), r.location.line, r.location.column))
    return results, suppressions


def _compute_crossfile(py_files: list[Path], config: Config, root: Path) -> CrossfileResult | None:
    """Run the opt-in cross-file resolution pre-pass, degrading gracefully.

    Returns a CrossfileResult (REG010 findings + the imported-handler Tier-3
    floor + semantic context), or None when REG010 is disabled or the LSP
    server is unavailable. A server failure is reported on stderr and the run
    continues without cross-file results — cross-file is opt-in tooling, not a
    reason to fail or abort an otherwise-clean check. REG010 set to ``off``
    suppresses its parity findings but the handler floor still applies.
    """
    rules = all_rules()
    if "REG010" not in rules or not rule_is_enabled("REG010", "REG", config.select, config.ignore):
        click.echo(
            "--crossfile given but REG010 is not enabled; add 'REG' to select. Skipping.",
            err=True,
        )
        return None
    meta, _ = rules["REG010"]
    severity = config.rule_severities.get("REG010", meta.default_severity)
    try:
        result = resolve_crossfile(py_files, config, root, severity)
    except LSPError as exc:
        click.echo(
            f"warning: cross-file analysis skipped — {exc} "
            f"(configure [tool.docpact.lsp] server or install docpact[crossfile]).",
            err=True,
        )
        return None
    if severity == Severity.OFF:
        # Parity findings suppressed; the Tier-3 floor still applies.
        return dataclasses.replace(result, findings=[])
    return result


def _compute_crossfile_for_semantic(
    py_files: list[Path], config: Config, root: Path
) -> CrossfileResult | None:
    """Resolve cross-file handlers/models for `semantic --crossfile`, degrading gracefully.

    Unlike check's pre-pass this is not gated on REG selection — `semantic`
    scopes by tier, not by `select` — and its REG010 findings are unused here
    (only the floor and context feed the semantic run). Returns None on a
    missing/failing server, with a note, so the semantic run still proceeds.
    """
    try:
        return resolve_crossfile(py_files, config, root, Severity.WARNING)
    except LSPError as exc:
        click.echo(
            f"warning: cross-file resolution skipped — {exc} "
            f"(configure [tool.docpact.lsp] server or install docpact[crossfile]).",
            err=True,
        )
        return None


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
    help="Rule codes or prefixes to enable (replaces config select). Comma-separated OK.",
)
@click.option(
    "--ignore",
    "cli_ignore",
    multiple=True,
    metavar="CODE",
    help="Rule codes or prefixes to disable (extends config ignore). Comma-separated OK.",
)
@click.option(
    "--extend-select",
    "cli_extend_select",
    multiple=True,
    metavar="CODE",
    help="Add rule codes or prefixes to the config's select set. Comma-separated OK.",
)
@click.option(
    "--extend-ignore",
    "cli_extend_ignore",
    multiple=True,
    metavar="CODE",
    help="Add rule codes or prefixes to the config's ignore set. Comma-separated OK.",
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
@click.option(
    "--crossfile",
    "crossfile",
    is_flag=True,
    help="Run opt-in cross-file rules (REG010) via the configured LSP server. "
    "Requires docpact[crossfile] or a [tool.docpact.lsp] server.",
)
@click.option(
    "--show-files",
    "show_files",
    is_flag=True,
    help="Print the list of files that would be checked and exit without running rules.",
)
@click.option(
    "--exit-non-zero-on-fix",
    "exit_non_zero_on_fix",
    is_flag=True,
    help="Exit 1 if --fix modified any files, even when no violations remain.",
)
@click.option(
    "--error-on-warning",
    "error_on_warning",
    is_flag=True,
    help="Treat warning-severity diagnostics as errors for the purpose of the exit code.",
)
@click.option(
    "--jobs",
    "-j",
    "jobs",
    type=click.IntRange(min=0),
    default=None,
    metavar="N",
    help="Worker processes for file analysis (0 = all cores, 1 = serial). "
    "Overrides config; default serial. Run 'docpact bench' to find your break-even.",
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
    crossfile: bool,
    show_files: bool,
    exit_non_zero_on_fix: bool,
    error_on_warning: bool,
    jobs: int | None,
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
    if jobs is not None:
        config = dataclasses.replace(config, jobs=jobs)

    py_files = _collect_py_files(paths, config, config_root)
    if config.respect_gitignore and not no_respect_gitignore:
        py_files = _filter_gitignored(py_files, Path.cwd())
    if changed_only is not None:
        changed_set = _get_changed_py_files(changed_only, Path.cwd())
        py_files = [f for f in py_files if f.resolve() in changed_set]

    if show_files:
        cwd = Path.cwd()
        for f in py_files:
            try:
                click.echo(f.relative_to(cwd).as_posix())
            except ValueError:
                click.echo(f.as_posix())
        sys.exit(0)

    # Cross-file pre-pass (ADR-009/ADR-010): opt-in via --crossfile. Runs before
    # per-file checks because its Tier-3 floor must be known at tier-assignment
    # time; one LSP session yields the floor and the REG010 findings together.
    crossfile_result = _compute_crossfile(py_files, config, config_root) if crossfile else None
    crossfile_floor = crossfile_result.floor if crossfile_result else frozenset()

    results, suppressions = _run_checks(py_files, config, config_root, crossfile_floor)

    apply_unsafe = unsafe_fixes and do_fix

    # --diff without --add-suppression shows fix preview and exits.
    if diff and not add_suppression:
        patch = diff_fixes(results, unsafe=apply_unsafe)
        if patch:
            click.echo(patch, nl=False)
        sys.exit(0)

    files_were_modified = False
    if do_fix:
        modified, conflicts = apply_fixes(results, unsafe=apply_unsafe)
        files_were_modified = bool(modified)
        for conflict in conflicts:
            click.echo(f"warning: {conflict}", err=True)
        # Re-run checks on modified files so reported results reflect post-fix state.
        if modified:
            results, suppressions = _run_checks(py_files, config, config_root, crossfile_floor)

    # Merge REG010 findings (not fixable) before suppression, so an inline
    # REG010 suppression still applies.
    if crossfile_result and crossfile_result.findings:
        results.extend(crossfile_result.findings)
        results.sort(key=lambda r: (str(r.location.file_path), r.location.line, r.location.column))

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
            if visible:
                parts.append(format_suppress_hint(config.suppress_comment[0]))
        output_str = "\n".join(parts)
    elif output_format == "json":
        output_str = format_json(visible, cwd=cwd)
    elif output_format == "sarif":
        output_str = format_sarif(visible, cwd=cwd)
    else:  # github
        output_str = format_github(visible, cwd=cwd)

    if output_file:
        Path(output_file).write_text(output_str + "\n" if output_str else "", encoding="utf-8")
    elif output_str:
        click.echo(output_str)

    should_exit_one = (files_were_modified and exit_non_zero_on_fix) or any(
        r.severity == Severity.ERROR or (error_on_warning and r.severity == Severity.WARNING)
        for r in visible
    )
    if should_exit_one and not exit_zero:
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

    rules = [
        (k, v) for k, v in sorted(all_rules().items(), key=lambda kv: kv[0]) if not v[0].reserved
    ]

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


def _peak_rss_mb(children: bool) -> float | None:
    """Return the high-water resident set size in MB, or None if unmeasurable.

    Uses getrusage, which is Unix-only. Returns None on Windows. The sys.platform
    guard also lets the type checker exclude the Unix-only `resource` members from
    Windows analysis. ru_maxrss is kilobytes on Linux and bytes on macOS.
    """
    if sys.platform == "win32":
        return None
    import resource

    who = resource.RUSAGE_CHILDREN if children else resource.RUSAGE_SELF
    raw = resource.getrusage(who).ru_maxrss
    return raw / (1024 * 1024) if sys.platform == "darwin" else raw / 1024


def _bench_config(paths: tuple[str, ...]) -> tuple[Config, Path, list[Path]]:
    """Load config and collect the files to benchmark for the given paths."""
    cfg_result = load_config(Path.cwd())
    config, root = cfg_result.config, cfg_result.root
    files = _collect_py_files(paths, config, root)
    if config.respect_gitignore:
        files = _filter_gitignored(files, Path.cwd())
    return config, root, files


def _bench_times(files: list[Path], config: Config, root: Path, runs: int) -> list[float]:
    """Return wall-clock seconds for each of `runs` full check passes under config."""
    import time

    out: list[float] = []
    for _ in range(runs):
        start = time.perf_counter()
        _run_checks(files, config, root)
        out.append(time.perf_counter() - start)
    return out


def _fmt_mb(value: float | None) -> str:
    """Format a memory value in MB, or an em dash when unmeasurable (e.g. Windows)."""
    return f"{value:.0f} MB" if value is not None else "—"


@main.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    "--runs",
    type=click.IntRange(min=1),
    default=3,
    show_default=True,
    help="Timed runs per configuration.",
)
@click.option(
    "--jobs",
    "-j",
    "jobs",
    type=click.IntRange(min=0),
    default=0,
    metavar="N",
    help="Worker count to benchmark against serial (0 = all cores).",
)
def bench(  # nodo: DOC012 -- click params; Args section would duplicate --help text
    paths: tuple[str, ...],
    runs: int,
    jobs: int,
) -> None:
    """Measure serial vs parallel analysis on your own tree and recommend a jobs value.

    The serial/parallel break-even depends on your project size, file complexity,
    core count, and OS — not on anything docpact can know in advance. This runs
    both on your actual files and reports wall-time and memory so you can decide.
    """
    import statistics

    config, root, files = _bench_config(paths)
    if not files:
        raise click.UsageError("no .py files found to benchmark")

    workers = _resolve_jobs(jobs)
    if workers == 1:
        workers = os.cpu_count() or 1
    serial_cfg = dataclasses.replace(config, jobs=1)
    parallel_cfg = dataclasses.replace(config, jobs=workers)

    click.echo(f"docpact bench — {len(files)} files, {runs} run(s) each, {workers} workers")
    if len(files) < 2:
        click.echo("note: <2 files; parallel cannot help here.")

    # Warm-up (filesystem + import caches) so the first timed run isn't penalized.
    _run_checks(files, serial_cfg, root)

    serial_times = _bench_times(files, serial_cfg, root, runs)
    serial_peak = _peak_rss_mb(children=False)  # in-process peak reflects serial work
    parallel_times = _bench_times(files, parallel_cfg, root, runs)
    worker_peak = _peak_rss_mb(children=True)  # largest single worker

    serial_med = statistics.median(serial_times)
    parallel_med = statistics.median(parallel_times)
    speedup = serial_med / parallel_med if parallel_med else 0.0

    click.echo("")
    click.echo(
        f"  serial (jobs=1):        {serial_med * 1000:8.1f} ms   peak {_fmt_mb(serial_peak)}"
    )
    click.echo(
        f"  parallel (jobs={workers}):"
        f"{'':>{max(0, 7 - len(str(workers)))}}{parallel_med * 1000:8.1f} ms"
        f"   ~{workers}x worker peak {_fmt_mb(worker_peak)}"
    )
    click.echo(f"  speedup: {speedup:.2f}x")
    click.echo("")

    # Recommend on time (reliably measured); memory is a caveat, not the driver.
    if speedup >= 1.15:
        click.echo(f"Recommendation: parallel is {speedup:.2f}x faster on this tree. Enable it:")
        click.echo("")
        click.echo("    [tool.docpact]")
        click.echo(f"    jobs = {workers}")
        click.echo("")
        click.echo(
            f"  Memory: each worker is a separate process (~{workers}x resident memory). "
            "Confirm that fits your CI before enabling."
        )
    else:
        click.echo(
            f"Recommendation: keep serial (jobs = 1). Parallel was only {speedup:.2f}x here — "
            "the process-startup overhead isn't worth it for this tree."
        )


def _collect_semantic_functions(
    py_files: list[Path],
    config: Config,
    root: Path,
    min_tier: int,
    crossfile_floor: frozenset[tuple[str, str]] = frozenset(),
) -> list[FunctionInfo]:
    """Collect functions at or above min_tier across the given files, in order.

    A function registered as an imported handler elsewhere (``crossfile_floor``,
    ADR-010) is promoted to a Tier-3 floor, so `semantic --crossfile` reviews the
    agent-facing handlers a file-local tier would miss.
    """
    out: list[FunctionInfo] = []
    for file_path in py_files:
        source_text = file_path.read_text(encoding="utf-8", errors="replace")
        all_names = parse_all_names(source_text)
        try:
            functions = extract_functions(file_path)
        except SyntaxError:
            continue
        floored_here = file_path.resolve().as_posix()
        for fn in functions:
            if fn.docstring_raw is None:
                continue
            tier = assign_tier(fn, config.tier_overrides, all_names=all_names, root=root)
            if (floored_here, fn.name) in crossfile_floor:
                tier = max(3, tier)
            if tier >= min_tier:
                out.append(fn)
    return out


@main.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    "--min-tier",
    type=click.IntRange(1, 4),
    default=None,
    help="Scope to this tier and above; default from config (3).",
)
@click.option("--dry-run", is_flag=True, help="Print the prompts that would be sent; no API call.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format.",
)
@click.option("--exit-zero", is_flag=True, help="Exit 0 even when findings are reported.")
@click.option(
    "--crossfile",
    "crossfile",
    is_flag=True,
    help="Resolve imported tool handlers/models via the LSP server: review the "
    "agent-facing handlers a file-local tier misses, and enrich prompts with the "
    "imported model's fields + registry description. Requires a [tool.docpact.lsp] server.",
)
def semantic(  # nodo: DOC012 -- click params; Args section would duplicate --help text
    paths: tuple[str, ...],
    min_tier: int | None,
    dry_run: bool,
    output_format: str,
    exit_zero: bool,
    crossfile: bool,
) -> None:
    """LLM-backed semantic docstring analysis (advisory, opt-in).

    Judges docstring *meaning* — cargo-cult restatement, an unsurfaced
    precondition/constraint, an empty Returns — which the deterministic `check`
    rules cannot. Non-deterministic and advisory; configure
    `[tool.docpact.semantic]` (backend, model, api_base, api_key_env). Use
    --dry-run to inspect prompts without an API call or sending any code.
    --crossfile additionally resolves imported tool handlers/models (ADR-010).
    """
    cfg_result = load_config(Path.cwd())
    config, root = cfg_result.config, cfg_result.root
    scope = min_tier if min_tier is not None else config.semantic.min_tier

    py_files = _collect_py_files(paths, config, root)

    # Cross-file resolution (ADR-010): floor promotes imported handlers into
    # scope; context enriches each prompt with the imported contract. Optional,
    # degrades gracefully if no server is available.
    floor: frozenset[tuple[str, str]] = frozenset()
    context: dict[tuple[str, str], str] = {}
    if crossfile:
        cf = _compute_crossfile_for_semantic(py_files, config, root)
        if cf is not None:
            floor, context = cf.floor, cf.context

    functions = _collect_semantic_functions(py_files, config, root, scope, floor)
    if not functions:
        click.echo(f"No functions in scope (tier >= {scope}).")
        return

    if dry_run:
        batches = _sem_build_batches(functions, context=context)
        click.echo(f"{len(functions)} functions → {len(batches)} request(s)\n")
        click.echo(f"=== SYSTEM ===\n{_SEM_SYSTEM}\n")
        for i, batch in enumerate(batches, 1):
            click.echo(f"=== REQUEST {i}/{len(batches)} ({len(batch)} functions) ===")
            click.echo(_sem_user_prompt(batch, context))
            click.echo("")
        click.echo("Dry run — no API call, no code sent.")
        return

    severity = config.rule_severities.get("SEM001", Severity.WARNING)
    try:
        backend = make_backend(config.semantic)
        report = _sem_analyze(functions, backend, severity=severity, context=context)
    except SemanticError as exc:
        raise click.UsageError(str(exc)) from exc

    if output_format == "json":
        click.echo(format_json(report.results, Path.cwd()))
    else:
        if report.results:
            click.echo(format_text(report.results, Path.cwd()))
        click.echo(
            f"Reviewed {report.functions_reviewed} function(s) in {report.requests} request(s); "
            f"{len(report.results)} finding(s). [advisory — non-deterministic]"
        )

    if report.results and not exit_zero:
        sys.exit(1)


if __name__ == "__main__":
    main()

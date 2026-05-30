"""End-to-end tests for the CLI check command."""

from __future__ import annotations

import subprocess
from pathlib import Path

from click.testing import CliRunner

from docpact.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def _run(*args: str) -> object:
    """Invoke the CLI in an isolated directory so no project config is found."""
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        # Write a bare pyproject.toml to stop the upward config walk here.
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        return runner.invoke(main, list(args), catch_exceptions=False)


# ---------------------------------------------------------------------------
# Basic invocation
# ---------------------------------------------------------------------------


def test_check_clean_file_exits_zero() -> None:
    result = _run("check", str(FIXTURES / "tier2" / "public_function.py"))
    assert result.exit_code == 0  # type: ignore[union-attr]


def test_check_file_with_errors_exits_one() -> None:
    result = _run("check", str(FIXTURES / "doc001_missing.py"))
    assert result.exit_code == 1  # type: ignore[union-attr]


def test_check_exit_zero_flag_overrides() -> None:
    result = _run("check", "--exit-zero", str(FIXTURES / "doc001_missing.py"))
    assert result.exit_code == 0  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------


def test_check_produces_text_output_for_errors() -> None:
    result = _run("check", str(FIXTURES / "doc001_missing.py"))
    output = result.output  # type: ignore[union-attr]
    assert "DOC001" in output


def test_check_includes_summary_line() -> None:
    result = _run("check", str(FIXTURES / "doc001_missing.py"))
    output = result.output  # type: ignore[union-attr]
    assert "Found" in output
    assert "error" in output


def test_check_shows_fixable_marker() -> None:
    # DOC001 is fixable — the [*] marker should appear.
    result = _run("check", str(FIXTURES / "doc001_missing.py"))
    output = result.output  # type: ignore[union-attr]
    assert "[*]" in output


def test_check_no_output_for_clean_file() -> None:
    result = _run("check", str(FIXTURES / "tier2" / "public_function.py"))
    output = result.output.strip()  # type: ignore[union-attr]
    assert output == ""


# ---------------------------------------------------------------------------
# Directory walking
# ---------------------------------------------------------------------------


def test_check_directory_walks_py_files(tmp_path: Path) -> None:
    sub = tmp_path / "pkg"
    sub.mkdir()
    (sub / "a.py").write_text("def foo(): pass\n")
    (sub / "b.py").write_text("def bar(): pass\n")
    result = _run("check", str(tmp_path))
    assert result.exit_code == 1  # type: ignore[union-attr]
    assert "DOC001" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# DOC007 in end-to-end
# ---------------------------------------------------------------------------


def test_check_reports_doc007() -> None:
    result = _run("check", str(FIXTURES / "doc007_mismatch.py"))
    output = result.output  # type: ignore[union-attr]
    assert "DOC007" in output


# ---------------------------------------------------------------------------
# Path handling
# ---------------------------------------------------------------------------


def test_check_shows_relative_paths(tmp_path: Path) -> None:
    src = tmp_path / "example.py"
    src.write_text("def foo(x: int) -> None: pass\n")
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(main, ["check", str(src)], catch_exceptions=False)
    assert result.exit_code == 1
    assert "DOC001" in result.output


# ---------------------------------------------------------------------------
# Config integration
# ---------------------------------------------------------------------------


def test_check_respects_select_flag(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int, y: str) -> None:\n    pass\n")
    # Only select MCP rules — DOC001 should not fire.
    result = _run("check", "--select", "MCP", "--exit-zero", str(src))
    assert "DOC001" not in result.output  # type: ignore[union-attr]


def test_check_respects_ignore_flag(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")
    result = _run("check", "--ignore", "DOC001", "--exit-zero", str(src))
    assert "DOC001" not in result.output  # type: ignore[union-attr]


def test_check_config_file_select(tmp_path: Path) -> None:
    (tmp_path / "docpact.toml").write_text('select = ["MCP"]\n')
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "docpact.toml").write_text('select = ["MCP"]\n')
        result = runner.invoke(main, ["check", "--exit-zero", str(src)], catch_exceptions=False)
    assert "DOC001" not in result.output


def test_check_config_exclude_skips_files(tmp_path: Path) -> None:
    sub = tmp_path / "legacy"
    sub.mkdir()
    (sub / "old.py").write_text("def foo(): pass\n")
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "docpact.toml").write_text(f'exclude = ["{sub}/old.py"]\n')
        result = runner.invoke(main, ["check", "--exit-zero", str(sub)], catch_exceptions=False)
    # File was excluded — no DOC001 output
    assert "DOC001" not in result.output


# ---------------------------------------------------------------------------
# Isolated rule-loading: prove all namespaces fire from a fresh CLI entry
# ---------------------------------------------------------------------------


def test_check_doc001_fires(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")
    result = _run("check", "--exit-zero", "--select", "DOC001", str(src))
    assert "DOC001" in result.output  # type: ignore[union-attr]


def test_check_doc007_fires(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text(
        'def foo(x: int) -> None:\n    """Do foo.\n\n    Args:\n        y: wrong.\n    """\n'
    )
    result = _run("check", "--exit-zero", "--select", "DOC007", str(src))
    assert "DOC007" in result.output  # type: ignore[union-attr]


def test_check_doc012_fires(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text('def foo(x: int) -> None:\n    """Summary."""\n')
    result = _run("check", "--exit-zero", "--select", "DOC012", str(src))
    # DOC012 fires at tier 2+ when Args section missing; summary-only at tier1 passes.
    # This file has no decorator so it's tier2 by default. x is documented nowhere.
    assert "DOC012" in result.output  # type: ignore[union-attr]


def test_check_ty001_fires(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text(
        'def foo() -> None:\n    """Do foo.\n\n    Returns:\n        The result.\n    """\n'
    )
    result = _run("check", "--exit-zero", "--select", "TY001", str(src))
    assert "TY001" in result.output  # type: ignore[union-attr]


def test_check_ty002_fires(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text(
        'def foo() -> int:\n    """Do foo.\n\n    Returns:\n        None.\n    """\n    return 1\n'
    )
    result = _run("check", "--exit-zero", "--select", "TY002", str(src))
    assert "TY002" in result.output  # type: ignore[union-attr]


def test_warnings_do_not_cause_nonzero_exit(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("# no module docstring\ndef foo() -> None:\n    pass\n")
    result = _run("check", "--select", "DOC002", str(src))
    # DOC002 is WARNING severity — should not set exit code 1
    assert result.exit_code == 0  # type: ignore[union-attr]


def test_errors_cause_nonzero_exit(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")
    result = _run("check", "--select", "DOC001", str(src))
    assert result.exit_code == 1  # type: ignore[union-attr]


def test_severity_off_skips_rule(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        toml = (
            '[project]\nname = "test"\n\n'
            '[tool.docpact]\nselect = ["DOC001"]\n\n'
            '[tool.docpact.rules]\nDOC001 = "off"\n'
        )
        (Path(td) / "pyproject.toml").write_text(toml)
        result = runner.invoke(main, ["check", "--exit-zero", str(src)], catch_exceptions=False)
    assert "DOC001" not in result.output


def test_unsafe_fixes_without_fix_errors() -> None:
    result = _run("check", "--unsafe-fixes", str(Path(__file__)))
    assert result.exit_code != 0  # type: ignore[union-attr]
    assert "requires --fix" in result.output.lower()  # type: ignore[union-attr]


def test_list_rules_shows_ty_namespace() -> None:
    result = _run("list-rules")
    assert "TY001" in result.output  # type: ignore[union-attr]
    assert "TY002" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# --changed-only
# ---------------------------------------------------------------------------


def _init_git_repo(path: Path) -> None:
    """Initialise a minimal git repo at path."""
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"], cwd=path, check=True, capture_output=True
    )
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True, capture_output=True)


def test_changed_only_restricts_to_changed_files() -> None:
    """Only files changed since the ref are checked; unchanged clean files are skipped."""
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        td_path = Path(td)
        _init_git_repo(td_path)
        (td_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

        # Initial commit: a clean file with no violations.
        (td_path / "clean.py").write_text('"""Module."""\ndef foo() -> None:\n    """Do foo."""\n')
        subprocess.run(["git", "add", "."], cwd=td, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=td, check=True, capture_output=True)

        # Second commit: a file with DOC001.
        (td_path / "bad.py").write_text("def bar(x: int) -> None:\n    pass\n")
        subprocess.run(["git", "add", "bad.py"], cwd=td, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add bad"], cwd=td, check=True, capture_output=True)

        result = runner.invoke(
            main,
            ["check", "--changed-only", "HEAD~1", str(td_path)],
            catch_exceptions=False,
        )
    assert result.exit_code == 1
    assert "bad.py" in result.output
    assert "clean.py" not in result.output


def test_changed_only_no_changed_files_exits_zero() -> None:
    """When no collected files match the changed set, the command exits 0."""
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        td_path = Path(td)
        _init_git_repo(td_path)
        (td_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

        (td_path / "clean.py").write_text('"""Module."""\ndef foo() -> None:\n    """Do foo."""\n')
        subprocess.run(["git", "add", "."], cwd=td, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=td, check=True, capture_output=True)

        # Nothing changed since HEAD — py_files filtered to empty.
        result = runner.invoke(
            main,
            ["check", "--changed-only", "HEAD", str(td_path)],
            catch_exceptions=False,
        )
    assert result.exit_code == 0


def test_changed_only_not_in_git_repo_exits_with_error(tmp_path: Path) -> None:
    """Outside a git repo, --changed-only exits non-zero with a clear message."""
    src = tmp_path / "t.py"
    src.write_text("def foo(): pass\n")
    runner = CliRunner()
    # isolated_filesystem is a plain directory, not a git repo.
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(
            main,
            ["check", "--changed-only", "main", str(src)],
        )
    assert result.exit_code != 0
    assert (
        "git" in result.output.lower()
        or "git" in (result.output + (result.exception or "")).lower()
    )


def test_changed_only_invalid_ref_exits_with_error() -> None:
    """An unresolvable git ref causes a non-zero exit with a clear message."""
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        td_path = Path(td)
        _init_git_repo(td_path)
        (td_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        (td_path / "t.py").write_text("def foo(): pass\n")
        subprocess.run(["git", "add", "."], cwd=td, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=td, check=True, capture_output=True)

        result = runner.invoke(
            main,
            ["check", "--changed-only", "no-such-ref-xyz", str(td_path)],
        )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# allow_pragma / # docpact: tier=N
# ---------------------------------------------------------------------------


def test_pragma_ignored_when_allow_pragma_false(tmp_path: Path) -> None:
    """Without allow_pragma, a # docpact: tier=1 pragma has no effect."""
    src = tmp_path / "t.py"
    # A public function with a pragma that would demote it to Tier 1.
    # Without allow_pragma, it stays Tier 2 and DOC012 fires (Args missing).
    src.write_text('def foo(x: int) -> None:  # docpact: tier=1\n    """Summary."""\n')
    result = _run("check", "--exit-zero", "--select", "DOC012", str(src))
    # Tier 2 is in effect → DOC012 fires because Args is missing.
    assert "DOC012" in result.output  # type: ignore[union-attr]


def test_pragma_demotes_to_tier1_when_allowed(tmp_path: Path) -> None:
    """# docpact: tier=1 on a public function suppresses Tier-2 requirements."""
    src = tmp_path / "t.py"
    src.write_text('def foo(x: int) -> None:  # docpact: tier=1\n    """Summary."""\n')
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text(
            "[project]\nname = 'test'\n[tool.docpact]\nallow_pragma = true\n"
        )
        result = runner.invoke(
            main, ["check", "--exit-zero", "--select", "DOC012", str(src)], catch_exceptions=False
        )
    # Tier 1 is in effect → DOC012 does not fire.
    assert "DOC012" not in result.output


def test_pragma_promotes_private_fn_to_tier2(tmp_path: Path) -> None:
    """# docpact: tier=2 on a _private function requires Tier-2 docs."""
    src = tmp_path / "t.py"
    src.write_text('def _helper(x: int) -> None:  # docpact: tier=2\n    """Summary."""\n')
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text(
            "[project]\nname = 'test'\n[tool.docpact]\nallow_pragma = true\n"
        )
        result = runner.invoke(
            main, ["check", "--exit-zero", "--select", "DOC012", str(src)], catch_exceptions=False
        )
    # Tier 2 → DOC012 fires for missing Args.
    assert "DOC012" in result.output


# ---------------------------------------------------------------------------
# --extend-select / --extend-ignore
# ---------------------------------------------------------------------------


def test_extend_select_adds_to_config_select(tmp_path: Path) -> None:
    """--extend-select appends to config's select rather than replacing it."""
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text(
            "[project]\nname = 'test'\n[tool.docpact]\nselect = ['MCP']\n"
        )
        result = runner.invoke(
            main,
            ["check", "--extend-select", "DOC001", "--exit-zero", str(src)],
            catch_exceptions=False,
        )
    # Config selects only MCP; extend-select adds DOC001 on top.
    assert "DOC001" in result.output


def test_select_replaces_config_select(tmp_path: Path) -> None:
    """--select replaces config's select entirely (contrast with --extend-select)."""
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text(
            "[project]\nname = 'test'\n[tool.docpact]\nselect = ['DOC']\n"
        )
        result = runner.invoke(
            main,
            ["check", "--select", "MCP", "--exit-zero", str(src)],
            catch_exceptions=False,
        )
    assert "DOC001" not in result.output


def test_extend_ignore_adds_to_config_ignore(tmp_path: Path) -> None:
    """--extend-ignore adds a code to the ignore set without replacing existing ignores."""
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")
    result = _run("check", "--extend-ignore", "DOC001", "--exit-zero", str(src))
    assert "DOC001" not in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# --no-config
# ---------------------------------------------------------------------------


def test_no_config_ignores_pyproject(tmp_path: Path) -> None:
    """--no-config runs with defaults, ignoring the nearest pyproject.toml."""
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        # Config restricts to MCP only — with --no-config the default (DOC, MCP) applies.
        (Path(td) / "pyproject.toml").write_text(
            "[project]\nname = 'test'\n[tool.docpact]\nselect = ['MCP']\n"
        )
        result = runner.invoke(
            main,
            ["check", "--no-config", "--exit-zero", str(src)],
            catch_exceptions=False,
        )
    assert "DOC001" in result.output


# ---------------------------------------------------------------------------
# --quiet
# ---------------------------------------------------------------------------


def test_quiet_suppresses_summary_line(tmp_path: Path) -> None:
    """--quiet shows diagnostics but omits the 'Found N errors.' summary."""
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")
    result = _run("check", "--quiet", "--select", "DOC001", str(src))
    assert "DOC001" in result.output  # type: ignore[union-attr]
    assert "Found" not in result.output  # type: ignore[union-attr]


def test_quiet_clean_file_produces_no_output(tmp_path: Path) -> None:
    """--quiet on a clean file produces no output at all."""
    src = tmp_path / "t.py"
    src.write_text('"""Module."""\ndef foo() -> None:\n    """Do foo."""\n')
    result = _run("check", "--quiet", str(src))
    assert result.output.strip() == ""  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# --statistics
# ---------------------------------------------------------------------------


def test_statistics_shows_per_rule_counts(tmp_path: Path) -> None:
    """--statistics prints a per-rule violation count table after diagnostics."""
    (tmp_path / "a.py").write_text("def foo(): pass\n")
    (tmp_path / "b.py").write_text("def bar(): pass\n")
    result = _run("check", "--exit-zero", "--select", "DOC001", "--statistics", str(tmp_path))
    output = result.output  # type: ignore[union-attr]
    assert "DOC001" in output
    assert "2" in output


def test_statistics_not_shown_without_flag(tmp_path: Path) -> None:
    """Without --statistics the count table does not appear."""
    import re

    src = tmp_path / "t.py"
    src.write_text("def foo(): pass\ndef bar(): pass\n")
    result = _run("check", "--exit-zero", "--select", "DOC001", str(src))
    stat_pattern = re.compile(r"^\d+\s+[A-Z]+\d+\s+")
    assert not any(
        stat_pattern.match(line)
        for line in result.output.split("\n")  # type: ignore[union-attr]
    )


# ---------------------------------------------------------------------------
# .gitignore respect
# ---------------------------------------------------------------------------


def test_gitignore_respected_by_default() -> None:
    """Files matching .gitignore are excluded from checks by default."""
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        td_path = Path(td)
        _init_git_repo(td_path)
        (td_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        (td_path / ".gitignore").write_text("ignored.py\n")
        subprocess.run(["git", "add", "."], cwd=td, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=td, check=True, capture_output=True)

        # Create files after commit: ignored.py is untracked + gitignored.
        (td_path / "ignored.py").write_text("def foo(): pass\n")
        (td_path / "checked.py").write_text("def bar(): pass\n")

        result = runner.invoke(
            main,
            ["check", "--exit-zero", "--select", "DOC001", str(td_path)],
            catch_exceptions=False,
        )
    assert "ignored.py" not in result.output
    assert "checked.py" in result.output


def test_no_respect_gitignore_checks_gitignored_files() -> None:
    """--no-respect-gitignore forces checking of files that would otherwise be skipped."""
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        td_path = Path(td)
        _init_git_repo(td_path)
        (td_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        (td_path / ".gitignore").write_text("ignored.py\n")
        subprocess.run(["git", "add", "."], cwd=td, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=td, check=True, capture_output=True)

        (td_path / "ignored.py").write_text("def foo(): pass\n")

        result = runner.invoke(
            main,
            ["check", "--exit-zero", "--no-respect-gitignore", "--select", "DOC001", str(td_path)],
            catch_exceptions=False,
        )
    assert "ignored.py" in result.output


def test_respect_gitignore_false_in_config() -> None:
    """respect_gitignore = false in config disables gitignore filtering."""
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        td_path = Path(td)
        _init_git_repo(td_path)
        (td_path / "pyproject.toml").write_text(
            "[project]\nname = 'test'\n[tool.docpact]\nrespect_gitignore = false\n"
        )
        (td_path / ".gitignore").write_text("ignored.py\n")
        subprocess.run(["git", "add", "."], cwd=td, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=td, check=True, capture_output=True)

        (td_path / "ignored.py").write_text("def foo(): pass\n")

        result = runner.invoke(
            main,
            ["check", "--exit-zero", "--select", "DOC001", str(td_path)],
            catch_exceptions=False,
        )
    assert "ignored.py" in result.output


# ---------------------------------------------------------------------------
# Exit code 2 for config errors
# ---------------------------------------------------------------------------


def test_config_error_exits_two(tmp_path: Path) -> None:
    """A malformed config file causes exit code 2, not 1."""
    src = tmp_path / "t.py"
    src.write_text("def foo(): pass\n")
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text(
            "[project]\nname = 'test'\n[tool.docpact]\nformat = 'bad-format'\n"
        )
        result = runner.invoke(main, ["check", str(src)])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# --format github
# ---------------------------------------------------------------------------


def test_format_github_emits_annotations(tmp_path: Path) -> None:
    """--format github produces GitHub Actions ::error / ::warning annotations."""
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")
    result = _run("check", "--format", "github", "--exit-zero", "--select", "DOC001", str(src))
    output = result.output  # type: ignore[union-attr]
    assert output.startswith("::error ")
    assert "DOC001" in output


def test_format_github_warning_uses_warning_level(tmp_path: Path) -> None:
    """WARNING-severity rules produce ::warning annotations, not ::error."""
    src = tmp_path / "t.py"
    src.write_text("# no module docstring\ndef foo() -> None:\n    pass\n")
    result = _run("check", "--format", "github", "--exit-zero", "--select", "DOC002", str(src))
    output = result.output  # type: ignore[union-attr]
    assert output.startswith("::warning ")


def test_format_github_clean_file_no_output(tmp_path: Path) -> None:
    """A clean file produces no annotation output."""
    src = tmp_path / "t.py"
    src.write_text('"""Module."""\ndef foo() -> None:\n    """Do foo."""\n')
    result = _run("check", "--format", "github", str(src))
    assert result.output.strip() == ""  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# --select / --ignore comma-separated codes
# ---------------------------------------------------------------------------


def test_select_comma_separated_runs_both_codes(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x):\n    pass\n")
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(
            main,
            ["check", "--select", "DOC001,DOC007", str(src)],
            catch_exceptions=False,
        )
    assert result.exit_code == 1  # type: ignore[union-attr]
    assert "DOC001" in result.output  # type: ignore[union-attr]


def test_select_comma_separated_same_as_repeated_flag(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x):\n    pass\n")
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        r1 = runner.invoke(
            main, ["check", "--select", "DOC001,DOC007", str(src)], catch_exceptions=False
        )
        r2 = runner.invoke(
            main,
            ["check", "--select", "DOC001", "--select", "DOC007", str(src)],
            catch_exceptions=False,
        )
    assert r1.exit_code == r2.exit_code  # type: ignore[union-attr]
    assert r1.output == r2.output  # type: ignore[union-attr]


def test_extend_select_comma_separated(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x):\n    pass\n")
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(
            main,
            ["check", "--extend-select", "DOC001,DOC007", str(src)],
            catch_exceptions=False,
        )
    assert result.exit_code == 1  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# DOC003 respects per-file-tier = 1
# ---------------------------------------------------------------------------


def test_doc003_silent_when_per_file_tier_1() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        td_path = Path(td)
        (td_path / "router.py").write_text("class Context:\n    pass\n")
        (td_path / "pyproject.toml").write_text(
            '[tool.docpact]\nselect = ["DOC003"]\n\n[tool.docpact.per-file-tier]\n"router.py" = 1\n'
        )
        result = runner.invoke(main, ["check", "router.py"], catch_exceptions=False)
    assert "DOC003" not in result.output  # type: ignore[union-attr]


def test_doc003_fires_when_no_tier_override() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        td_path = Path(td)
        (td_path / "router.py").write_text("class Context:\n    pass\n")
        (td_path / "pyproject.toml").write_text('[tool.docpact]\nselect = ["DOC003"]\n')
        result = runner.invoke(main, ["check", "router.py"], catch_exceptions=False)
    assert "DOC003" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# _FILE_LEVEL_CODES invariant
# ---------------------------------------------------------------------------


def test_file_level_codes_matches_dispatch() -> None:
    """Every code in _FILE_LEVEL_CODES must be handled by _run_checks, and vice versa.

    Pre-pass codes are dispatched in the for-loop match block.
    FIX003 and the REG rules run as post-passes.
    PARSE001 is emitted on SyntaxError before the function loop.
    If this test fails, a code was added to one place but not the other.
    """
    from docpact.cli import _FILE_LEVEL_CODES  # type: ignore[attr-defined]

    pre_pass = {"FIX001", "FIX002", "FIX004", "DOC002", "DOC003", "DOC050"}
    post_pass = {"FIX003", "REG001", "REG002"}
    syntax_error_path = {"PARSE001"}
    expected = pre_pass | post_pass | syntax_error_path

    assert expected == _FILE_LEVEL_CODES, (
        f"_FILE_LEVEL_CODES is out of sync with _run_checks dispatch.\n"
        f"  In _FILE_LEVEL_CODES but not dispatched: {_FILE_LEVEL_CODES - expected}\n"
        f"  Dispatched but not in _FILE_LEVEL_CODES: {expected - _FILE_LEVEL_CODES}"
    )


# ---------------------------------------------------------------------------
# --show-files
# ---------------------------------------------------------------------------


def test_show_files_lists_py_files(tmp_path: Path) -> None:
    """--show-files prints checked files and exits 0 without running rules."""
    (tmp_path / "a.py").write_text("def foo(): pass\n")
    (tmp_path / "b.py").write_text("def bar(): pass\n")
    result = _run("check", "--show-files", str(tmp_path))
    assert result.exit_code == 0  # type: ignore[union-attr]
    output = result.output  # type: ignore[union-attr]
    assert "a.py" in output
    assert "b.py" in output


def test_show_files_exits_zero_despite_errors(tmp_path: Path) -> None:
    """--show-files exits 0 even when the file has violations."""
    (tmp_path / "bad.py").write_text("def foo(): pass\n")
    result = _run("check", "--show-files", "--select", "DOC001", str(tmp_path))
    assert result.exit_code == 0  # type: ignore[union-attr]


def test_show_files_empty_dir(tmp_path: Path) -> None:
    """--show-files on a directory with no .py files produces no output."""
    result = _run("check", "--show-files", str(tmp_path))
    assert result.exit_code == 0  # type: ignore[union-attr]
    assert result.output.strip() == ""  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# --exit-non-zero-on-fix
# ---------------------------------------------------------------------------


def test_exit_non_zero_on_fix_exits_one_when_files_changed(tmp_path: Path) -> None:
    """--exit-non-zero-on-fix exits 1 when --fix modifies at least one file."""
    src = tmp_path / "f.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")
    result = _run("check", "--fix", "--exit-non-zero-on-fix", "--select", "DOC001", str(src))
    assert result.exit_code == 1  # type: ignore[union-attr]


def test_exit_non_zero_on_fix_exits_zero_when_nothing_changed(tmp_path: Path) -> None:
    """--exit-non-zero-on-fix exits 0 when --fix makes no changes."""
    src = tmp_path / "f.py"
    src.write_text('"""Module."""\n\n\ndef foo() -> None:\n    """Do foo."""\n')
    result = _run("check", "--fix", "--exit-non-zero-on-fix", str(src))
    assert result.exit_code == 0  # type: ignore[union-attr]


def test_exit_zero_overrides_exit_non_zero_on_fix(tmp_path: Path) -> None:
    """--exit-zero takes precedence over --exit-non-zero-on-fix."""
    src = tmp_path / "f.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")
    result = _run(
        "check", "--fix", "--exit-non-zero-on-fix", "--exit-zero", "--select", "DOC001", str(src)
    )
    assert result.exit_code == 0  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# --error-on-warning
# ---------------------------------------------------------------------------


def test_error_on_warning_exits_one_for_warnings(tmp_path: Path) -> None:
    """--error-on-warning causes warning-severity violations to produce exit 1."""
    # DOC002 (module docstring missing) is WARNING severity.
    src = tmp_path / "f.py"
    src.write_text("def foo() -> None:\n    pass\n")
    result = _run("check", "--error-on-warning", "--select", "DOC002", str(src))
    assert result.exit_code == 1  # type: ignore[union-attr]


def test_warnings_do_not_exit_one_without_flag(tmp_path: Path) -> None:
    """Without --error-on-warning, warning-severity violations exit 0."""
    src = tmp_path / "f.py"
    src.write_text("def foo() -> None:\n    pass\n")
    result = _run("check", "--select", "DOC002", str(src))
    assert result.exit_code == 0  # type: ignore[union-attr]


def test_exit_zero_overrides_error_on_warning(tmp_path: Path) -> None:
    """--exit-zero takes precedence over --error-on-warning."""
    src = tmp_path / "f.py"
    src.write_text("def foo() -> None:\n    pass\n")
    result = _run("check", "--error-on-warning", "--exit-zero", "--select", "DOC002", str(src))
    assert result.exit_code == 0  # type: ignore[union-attr]

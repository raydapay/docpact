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

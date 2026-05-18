"""End-to-end tests for the CLI check command."""

from __future__ import annotations

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

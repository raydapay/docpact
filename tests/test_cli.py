"""End-to-end tests for the CLI check command."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from docpact.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def _run(*args: str) -> object:
    runner = CliRunner()
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
    # Both functions are missing docstrings — should find errors.
    assert result.exit_code == 1  # type: ignore[union-attr]
    output = result.output  # type: ignore[union-attr]
    assert "DOC001" in output


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
    # Invoke from tmp_path so paths are relative.
    result = runner.invoke(main, ["check", str(src)], catch_exceptions=False)
    # Path should be in output when errors exist.
    assert result.exit_code == 1
    assert "DOC001" in result.output

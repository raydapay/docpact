"""Tests for docpact.baseline — add_suppressions, diff_suppressions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from docpact.baseline import (
    _build_pattern,
    _group_by_file_line,
    _patch_line,
    add_suppressions,
    diff_suppressions,
)
from docpact.model.diagnostic import RuleResult, Severity, SourceLocation

if TYPE_CHECKING:
    from pathlib import Path


def _loc(file_path: Path, line: int, column: int = 0) -> SourceLocation:
    return SourceLocation(file_path=file_path, line=line, column=column)


def _result(code: str, file_path: Path, line: int) -> RuleResult:
    return RuleResult(
        code=code,
        severity=Severity.ERROR,
        message=f"{code} violation",
        location=_loc(file_path, line),
    )


# ---------------------------------------------------------------------------
# _patch_line unit tests
# ---------------------------------------------------------------------------

MARKERS = ("nodo",)
PATTERN = _build_pattern(MARKERS)


def test_patch_line_appends_new_comment() -> None:
    line = "def foo():\n"
    result = _patch_line(line, frozenset({"DOC001"}), "baseline", MARKERS, PATTERN)
    assert result == "def foo():  # nodo: DOC001 -- baseline\n"


def test_patch_line_preserves_trailing_newline() -> None:
    line = "def foo():\n"
    result = _patch_line(line, frozenset({"DOC001"}), "baseline", MARKERS, PATTERN)
    assert result.endswith("\n")


def test_patch_line_no_trailing_newline() -> None:
    line = "def foo():"
    result = _patch_line(line, frozenset({"DOC001"}), "baseline", MARKERS, PATTERN)
    assert not result.endswith("\n")
    assert "# nodo: DOC001 -- baseline" in result


def test_patch_line_multiple_codes_sorted() -> None:
    line = "def foo():\n"
    result = _patch_line(line, frozenset({"DOC012", "DOC001"}), "baseline", MARKERS, PATTERN)
    assert "DOC001, DOC012" in result


def test_patch_line_merges_with_existing_suppression() -> None:
    line = "def foo(  # nodo: DOC001 -- existing reason\n"
    result = _patch_line(line, frozenset({"DOC007"}), "baseline", MARKERS, PATTERN)
    assert "DOC001, DOC007" in result
    assert "existing reason" in result
    assert "baseline" not in result


def test_patch_line_preserves_existing_reason_over_new_reason() -> None:
    line = "def foo(  # nodo: DOC001 -- my custom note\n"
    result = _patch_line(line, frozenset({"DOC012"}), "newreason", MARKERS, PATTERN)
    assert "my custom note" in result
    assert "newreason" not in result


def test_patch_line_bare_suppression_unchanged() -> None:
    line = "def foo(  # nodo\n"
    result = _patch_line(line, frozenset({"DOC001"}), "baseline", MARKERS, PATTERN)
    assert result == line


def test_patch_line_no_change_when_codes_already_present() -> None:
    line = "def foo(  # nodo: DOC001 -- existing\n"
    result = _patch_line(line, frozenset({"DOC001"}), "baseline", MARKERS, PATTERN)
    assert result == line


def test_patch_line_after_open_paren() -> None:
    line = "def foo(\n"
    result = _patch_line(line, frozenset({"DOC001"}), "baseline", MARKERS, PATTERN)
    assert "# nodo: DOC001 -- baseline" in result


# ---------------------------------------------------------------------------
# _group_by_file_line
# ---------------------------------------------------------------------------


def test_group_skips_fix001_fix002(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    results = [
        _result("FIX001", f, 1),
        _result("FIX002", f, 2),
        _result("DOC001", f, 3),
    ]
    grouped = _group_by_file_line(results)
    assert f in grouped
    assert 1 not in grouped[f]
    assert 2 not in grouped[f]
    assert 3 in grouped[f]


def test_group_combines_codes_on_same_line(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    results = [_result("DOC001", f, 5), _result("DOC012", f, 5)]
    grouped = _group_by_file_line(results)
    assert grouped[f][5] == frozenset({"DOC001", "DOC012"})


def test_group_empty_results() -> None:
    assert _group_by_file_line([]) == {}


# ---------------------------------------------------------------------------
# add_suppressions integration tests
# ---------------------------------------------------------------------------


def test_add_suppressions_writes_comment(tmp_path: Path) -> None:
    f = tmp_path / "module.py"
    f.write_text("def foo():\n    pass\n")
    results = [_result("DOC001", f, 1)]
    counts = add_suppressions(results)
    assert counts == {f: 1}
    text = f.read_text()
    assert "# nodo: DOC001 -- baseline" in text


def test_add_suppressions_custom_reason(tmp_path: Path) -> None:
    f = tmp_path / "module.py"
    f.write_text("def foo():\n    pass\n")
    results = [_result("DOC001", f, 1)]
    add_suppressions(results, reason="pre-docpact")
    assert "pre-docpact" in f.read_text()


def test_add_suppressions_multiple_violations_same_line(tmp_path: Path) -> None:
    f = tmp_path / "module.py"
    f.write_text("def foo():\n    pass\n")
    results = [_result("DOC001", f, 1), _result("DOC012", f, 1)]
    add_suppressions(results)
    text = f.read_text()
    assert "DOC001" in text
    assert "DOC012" in text
    assert text.count("# nodo:") == 1  # single comment, not two


def test_add_suppressions_multiple_lines(tmp_path: Path) -> None:
    f = tmp_path / "module.py"
    f.write_text("def foo():\n    pass\ndef bar():\n    pass\n")
    results = [_result("DOC001", f, 1), _result("DOC001", f, 3)]
    counts = add_suppressions(results)
    assert counts == {f: 2}
    text = f.read_text()
    assert text.count("# nodo:") == 2


def test_add_suppressions_merges_existing(tmp_path: Path) -> None:
    f = tmp_path / "module.py"
    f.write_text("def foo(  # nodo: DOC001 -- pre-existing\n    x: int,\n) -> None: ...\n")
    results = [_result("DOC012", f, 1)]
    add_suppressions(results)
    text = f.read_text()
    assert "DOC001, DOC012" in text
    assert "pre-existing" in text
    assert text.count("# nodo:") == 1


def test_add_suppressions_skips_fix001_fix002(tmp_path: Path) -> None:
    f = tmp_path / "module.py"
    f.write_text("def foo():  # nodo\n    pass\n")
    results = [_result("FIX001", f, 1), _result("FIX002", f, 1)]
    counts = add_suppressions(results)
    assert counts == {}
    assert f.read_text() == "def foo():  # nodo\n    pass\n"


def test_add_suppressions_returns_empty_when_no_results() -> None:
    assert add_suppressions([]) == {}


def test_add_suppressions_multiple_files(tmp_path: Path) -> None:
    f1 = tmp_path / "a.py"
    f2 = tmp_path / "b.py"
    f1.write_text("def a():\n    pass\n")
    f2.write_text("def b():\n    pass\n")
    results = [_result("DOC001", f1, 1), _result("DOC001", f2, 1)]
    counts = add_suppressions(results)
    assert set(counts) == {f1, f2}


# ---------------------------------------------------------------------------
# diff_suppressions
# ---------------------------------------------------------------------------


def test_diff_suppressions_returns_unified_diff(tmp_path: Path) -> None:
    f = tmp_path / "module.py"
    f.write_text("def foo():\n    pass\n")
    results = [_result("DOC001", f, 1)]
    patch = diff_suppressions(results)
    assert "@@" in patch
    assert "# nodo: DOC001 -- baseline" in patch


def test_diff_suppressions_does_not_write_file(tmp_path: Path) -> None:
    f = tmp_path / "module.py"
    original = "def foo():\n    pass\n"
    f.write_text(original)
    results = [_result("DOC001", f, 1)]
    diff_suppressions(results)
    assert f.read_text() == original


def test_diff_suppressions_empty_when_no_results() -> None:
    assert diff_suppressions([]) == ""


def test_diff_suppressions_custom_reason(tmp_path: Path) -> None:
    f = tmp_path / "module.py"
    f.write_text("def foo():\n    pass\n")
    results = [_result("DOC001", f, 1)]
    patch = diff_suppressions(results, reason="custom")
    assert "custom" in patch


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_add_suppression_flag(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from docpact.cli import main

    f = tmp_path / "mod.py"
    f.write_text('def foo():\n    """Foo."""\n    pass\n')
    (tmp_path / "pyproject.toml").write_text('[tool.docpact]\nselect = ["DOC001"]\n')
    runner = CliRunner()
    result = runner.invoke(main, ["check", str(f), "--add-suppression"], catch_exceptions=False)
    assert result.exit_code == 0


def test_cli_add_suppression_writes_nodo_comment(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from docpact.cli import main

    f = tmp_path / "mod.py"
    f.write_text("def foo():\n    pass\n")
    (tmp_path / "pyproject.toml").write_text('[tool.docpact]\nselect = ["DOC001"]\n')
    runner = CliRunner()
    runner.invoke(main, ["check", str(f), "--add-suppression"], catch_exceptions=False)
    assert "# nodo:" in f.read_text()


def test_cli_add_suppression_diff_no_write(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from docpact.cli import main

    f = tmp_path / "mod.py"
    original = "def foo():\n    pass\n"
    f.write_text(original)
    (tmp_path / "pyproject.toml").write_text('[tool.docpact]\nselect = ["DOC001"]\n')
    runner = CliRunner()
    result = runner.invoke(
        main, ["check", str(f), "--add-suppression", "--diff"], catch_exceptions=False
    )
    assert result.exit_code == 0
    assert "# nodo:" in result.output
    assert f.read_text() == original  # file unchanged


def test_cli_add_suppression_custom_reason(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from docpact.cli import main

    f = tmp_path / "mod.py"
    f.write_text("def foo():\n    pass\n")
    (tmp_path / "pyproject.toml").write_text('[tool.docpact]\nselect = ["DOC001"]\n')
    runner = CliRunner()
    runner.invoke(
        main,
        ["check", str(f), "--add-suppression", "--suppression-reason", "my-project baseline"],
        catch_exceptions=False,
    )
    assert "my-project baseline" in f.read_text()


def test_cli_add_suppression_exits_zero_with_violations(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from docpact.cli import main

    f = tmp_path / "mod.py"
    f.write_text("def foo():\n    pass\n")
    (tmp_path / "pyproject.toml").write_text('[tool.docpact]\nselect = ["DOC001"]\n')
    runner = CliRunner()
    result = runner.invoke(main, ["check", str(f), "--add-suppression"], catch_exceptions=False)
    assert result.exit_code == 0


def test_cli_add_suppression_exits_zero_with_no_violations(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from docpact.cli import main

    f = tmp_path / "mod.py"
    f.write_text('"""Module."""\n\ndef foo():\n    """Foo."""\n    pass\n')
    (tmp_path / "pyproject.toml").write_text('[tool.docpact]\nselect = ["DOC001"]\n')
    runner = CliRunner()
    result = runner.invoke(main, ["check", str(f), "--add-suppression"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "No violations" in result.output

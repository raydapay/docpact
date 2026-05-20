"""Tests for docpact.output — format_text, format_json, format_github, format_summary."""

from __future__ import annotations

import json
from pathlib import Path

from docpact.model.diagnostic import Fix, RuleResult, Severity, SourceLocation
from docpact.output import (
    format_github,
    format_json,
    format_summary,
    format_suppress_hint,
    format_text,
)


def _loc(path: Path, line: int = 1, col: int = 0) -> SourceLocation:
    return SourceLocation(file_path=path, line=line, column=col)


def _fix(path: Path, desc: str = "fix it") -> Fix:
    return Fix(description=desc, file_path=path, start_offset=0, end_offset=0, replacement="x")


def _result(
    path: Path,
    code: str = "DOC001",
    line: int = 1,
    fix: Fix | None = None,
    unsafe_fix: Fix | None = None,
) -> RuleResult:
    return RuleResult(
        code=code,
        severity=Severity.ERROR,
        message=f"{code} message",
        location=_loc(path, line),
        fix=fix,
        unsafe_fix=unsafe_fix,
    )


# ---------------------------------------------------------------------------
# format_text
# ---------------------------------------------------------------------------


def test_format_text_empty_returns_empty_string(tmp_path: Path) -> None:
    assert format_text([]) == ""


def test_format_text_basic_structure(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    r = _result(f)
    text = format_text([r])
    assert "DOC001" in text
    assert "DOC001 message" in text
    assert "1:0" in text


def test_format_text_relative_path(tmp_path: Path) -> None:
    sub = tmp_path / "pkg"
    sub.mkdir()
    f = sub / "foo.py"
    r = _result(f)
    text = format_text([r], cwd=tmp_path)
    assert "pkg/foo.py" in text
    assert str(tmp_path) not in text


def test_format_text_fixable_marker(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    r = _result(f, fix=_fix(f))
    text = format_text([r])
    assert "[*]" in text


def test_format_text_no_fixable_marker_when_no_fix(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    r = _result(f)
    assert "[*]" not in format_text([r])


def test_format_text_help_line(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    fix = _fix(f, desc="Insert stub docstring")
    r = _result(f, fix=fix)
    text = format_text([r])
    assert "= help: Insert stub docstring" in text


def test_format_text_no_help_line_without_fix(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    assert "= help:" not in format_text([_result(f)])


def test_format_text_multiple_results(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    results = [_result(f, "DOC001", line=1), _result(f, "DOC007", line=5)]
    text = format_text(results)
    assert "DOC001" in text
    assert "DOC007" in text


# ---------------------------------------------------------------------------
# format_json
# ---------------------------------------------------------------------------


def test_format_json_is_valid_json(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    output = format_json([_result(f)])
    doc = json.loads(output)
    assert isinstance(doc, dict)


def test_format_json_empty_results(tmp_path: Path) -> None:
    doc = json.loads(format_json([]))
    assert doc["version"] == "1"
    assert doc["diagnostics"] == []
    assert doc["summary"]["total"] == 0


def test_format_json_version_field(tmp_path: Path) -> None:
    doc = json.loads(format_json([_result(tmp_path / "f.py")]))
    assert doc["version"] == "1"


def test_format_json_diagnostic_fields(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    r = _result(f, "DOC007", line=3)
    doc = json.loads(format_json([r]))
    diag = doc["diagnostics"][0]
    assert diag["code"] == "DOC007"
    assert diag["severity"] == "error"
    assert "DOC007 message" in diag["message"]
    assert diag["location"]["line"] == 3
    assert diag["location"]["column"] == 0
    assert diag["fixable"] is False
    assert diag["unsafe_fixable"] is False


def test_format_json_fixable_flags(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    safe_fix = _fix(f)
    unsafe_fix = _fix(f, desc="unsafe")
    r = RuleResult(
        code="DOC001",
        severity=Severity.ERROR,
        message="msg",
        location=_loc(f),
        fix=safe_fix,
        unsafe_fix=unsafe_fix,
    )
    doc = json.loads(format_json([r]))
    diag = doc["diagnostics"][0]
    assert diag["fixable"] is True
    assert diag["unsafe_fixable"] is True


def test_format_json_summary_counts(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    r1 = _result(f, "DOC001", fix=_fix(f))
    r2 = _result(f, "DOC007")
    doc = json.loads(format_json([r1, r2]))
    assert doc["summary"]["total"] == 2
    assert doc["summary"]["fixable"] == 1
    assert doc["summary"]["unsafe_fixable"] == 0


def test_format_json_relative_path(tmp_path: Path) -> None:
    sub = tmp_path / "pkg"
    sub.mkdir()
    f = sub / "foo.py"
    doc = json.loads(format_json([_result(f)], cwd=tmp_path))
    assert doc["diagnostics"][0]["location"]["file"] == "pkg/foo.py"


# ---------------------------------------------------------------------------
# format_summary
# ---------------------------------------------------------------------------


def test_format_summary_empty_returns_empty(tmp_path: Path) -> None:
    assert format_summary([]) == ""


def test_format_summary_singular(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    assert "1 error" in format_summary([_result(f)])


def test_format_summary_plural(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    assert "2 errors" in format_summary([_result(f), _result(f, "DOC007")])


def test_format_summary_warning_only(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    r = RuleResult(
        code="DOC002",
        severity=Severity.WARNING,
        message="msg",
        location=_loc(f),
    )
    s = format_summary([r])
    assert "1 warning" in s
    assert "error" not in s


def test_format_summary_mixed_errors_and_warnings(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    err = _result(f, "DOC001")
    warn = RuleResult(code="DOC002", severity=Severity.WARNING, message="msg", location=_loc(f))
    s = format_summary([err, warn])
    assert "1 error" in s
    assert "1 warning" in s


def test_format_summary_fixable(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    r = _result(f, fix=_fix(f))
    assert "--fix" in format_summary([r])


def test_format_summary_no_fixable_part_when_none(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    assert "--fix" not in format_summary([_result(f)])


def test_format_summary_unsafe(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    r = RuleResult(
        code="MCP001",
        severity=Severity.ERROR,
        message="msg",
        location=_loc(f),
        unsafe_fix=_fix(f),
    )
    assert "--unsafe-fixes" in format_summary([r])


# ---------------------------------------------------------------------------
# format_github
# ---------------------------------------------------------------------------


def test_format_github_empty_returns_empty_string(tmp_path: Path) -> None:
    assert format_github([]) == ""


def test_format_github_error_level(tmp_path: Path) -> None:
    r = _result(tmp_path / "f.py")  # Severity.ERROR
    line = format_github([r])
    assert line.startswith("::error ")


def test_format_github_warning_level(tmp_path: Path) -> None:
    f = tmp_path / "f.py"
    r = RuleResult(code="DOC001", severity=Severity.WARNING, message="msg", location=_loc(f))
    line = format_github([r])
    assert line.startswith("::warning ")


def test_format_github_contains_file_and_line(tmp_path: Path) -> None:
    f = tmp_path / "src" / "foo.py"
    r = _result(f, line=42)
    line = format_github([r])
    assert "foo.py" in line
    assert "line=42" in line


def test_format_github_column_is_one_based(tmp_path: Path) -> None:
    f = tmp_path / "f.py"
    r = RuleResult(code="DOC001", severity=Severity.ERROR, message="msg", location=_loc(f, col=0))
    line = format_github([r])
    assert "col=1" in line


def test_format_github_title_is_code(tmp_path: Path) -> None:
    f = tmp_path / "f.py"
    r = _result(f, code="DOC007")
    line = format_github([r])
    assert "title=DOC007" in line


def test_format_github_message_appended(tmp_path: Path) -> None:
    f = tmp_path / "f.py"
    r = RuleResult(
        code="DOC001", severity=Severity.ERROR, message="param x missing", location=_loc(f)
    )
    line = format_github([r])
    assert line.endswith("::param x missing")


def test_format_github_double_colon_in_message_is_escaped(tmp_path: Path) -> None:
    f = tmp_path / "f.py"
    r = RuleResult(code="DOC001", severity=Severity.ERROR, message="a::b", location=_loc(f))
    line = format_github([r])
    assert "a%3A%3Ab" in line
    assert "a::b" not in line.split("::")[-1]


def test_format_github_relative_path_when_cwd_provided(tmp_path: Path) -> None:
    sub = tmp_path / "pkg"
    sub.mkdir()
    f = sub / "foo.py"
    r = _result(f)
    line = format_github([r], cwd=tmp_path)
    assert "pkg/foo.py" in line
    assert str(tmp_path) not in line


def test_format_github_multiple_results_one_line_each(tmp_path: Path) -> None:
    f = tmp_path / "f.py"
    results = [_result(f, line=1), _result(f, line=2)]
    output = format_github(results)
    assert len(output.splitlines()) == 2


def test_format_github_cli_format(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from docpact.cli import main

    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")

    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(
            main,
            ["check", "--format", "github", "--exit-zero", str(src)],
            catch_exceptions=False,
        )

    assert result.exit_code == 0
    assert "::error " in result.output or "::warning " in result.output


# ---------------------------------------------------------------------------
# format_suppress_hint
# ---------------------------------------------------------------------------


def test_format_suppress_hint_contains_marker() -> None:
    hint = format_suppress_hint("nodo")
    assert "# nodo: CODE -- reason" in hint
    assert "--add-suppression" in hint


def test_format_suppress_hint_custom_marker() -> None:
    hint = format_suppress_hint("mymarker")
    assert "# mymarker:" in hint


# ---------------------------------------------------------------------------
# CLI integration: --format json and noqa suppression
# ---------------------------------------------------------------------------


def test_cli_json_output(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from docpact.cli import main

    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")

    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(
            main,
            ["check", "--format", "json", "--exit-zero", str(src)],
            catch_exceptions=False,
        )

    doc = json.loads(result.output)
    assert doc["version"] == "1"
    assert any(d["code"] == "DOC001" for d in doc["diagnostics"])


def test_cli_nodo_suppresses_diagnostic(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from docpact.cli import main

    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:  # nodo: DOC001\n    pass\n")

    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(
            main,
            ["check", "--exit-zero", str(src)],
            catch_exceptions=False,
        )

    assert "DOC001" not in result.output
    assert result.exit_code == 0


def test_cli_nodo_with_wrong_code_does_not_suppress(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from docpact.cli import main

    src = tmp_path / "t.py"

    src.write_text("def foo(x: int) -> None:  # nodo: DOC007\n    pass\n")

    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(
            main,
            ["check", "--exit-zero", str(src)],
            catch_exceptions=False,
        )

    assert "DOC001" in result.output


def test_cli_hint_shown_when_violations(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from docpact.cli import main

    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")

    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(main, ["check", "--exit-zero", str(src)], catch_exceptions=False)

    assert "hint:" in result.output
    assert "nodo" in result.output
    assert "--add-suppression" in result.output


def test_cli_hint_not_shown_when_no_violations(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from docpact.cli import main

    src = tmp_path / "t.py"
    src.write_text(
        '"""Module."""\n\n\ndef foo(x: int) -> None:\n'
        '    """Do foo.\n\n    Args:\n        x: An integer.\n    """\n'
    )

    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(main, ["check", "--exit-zero", str(src)], catch_exceptions=False)

    assert "hint:" not in result.output


def test_cli_hint_not_shown_when_quiet(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from docpact.cli import main

    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")

    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(
            main, ["check", "--quiet", "--exit-zero", str(src)], catch_exceptions=False
        )

    assert "hint:" not in result.output

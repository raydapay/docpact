"""Tests for PARSE001 — Python syntax error rule."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from docpact.cli import main
from docpact.model.diagnostic import Severity
from docpact.model.function_info import FunctionInfo
from docpact.rules._registry import RuleConfig
from docpact.rules.parse.parse001_syntax_error import check, check_syntax_error

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(severity: Severity = Severity.ERROR) -> RuleConfig:
    return RuleConfig(severity=severity, options={})


def _syntax_error(source: str) -> SyntaxError:
    """Compile source and return the SyntaxError it raises."""
    with pytest.raises(SyntaxError) as exc_info:
        ast.parse(source)
    return exc_info.value


def _bad_file(tmp_path: Path) -> Path:
    p = tmp_path / "bad.py"
    p.write_text("def (\n")
    return p


# ---------------------------------------------------------------------------
# Unit tests for check_syntax_error
# ---------------------------------------------------------------------------


def test_syntax_error_fires(tmp_path: Path) -> None:
    exc = _syntax_error("def (:\n")
    result = check_syntax_error(exc, tmp_path / "bad.py", _cfg())
    assert result.code == "PARSE001"
    assert result.severity == Severity.ERROR


def test_syntax_error_line_reported(tmp_path: Path) -> None:
    exc = _syntax_error("def (:\n")
    result = check_syntax_error(exc, tmp_path / "bad.py", _cfg())
    assert result.location.line == exc.lineno


def test_syntax_error_column_reported(tmp_path: Path) -> None:
    exc = _syntax_error("def (:\n")
    result = check_syntax_error(exc, tmp_path / "bad.py", _cfg())
    assert exc.offset is not None and exc.offset > 0
    assert result.location.column == exc.offset - 1


def test_syntax_error_message_contains_msg(tmp_path: Path) -> None:
    exc = _syntax_error("def (:\n")
    result = check_syntax_error(exc, tmp_path / "bad.py", _cfg())
    assert exc.msg in result.message


def test_syntax_error_none_lineno_falls_back_to_line_1(tmp_path: Path) -> None:
    exc = SyntaxError("invalid syntax")
    exc.lineno = None
    exc.offset = None
    result = check_syntax_error(exc, tmp_path / "bad.py", _cfg())
    assert result.location.line == 1
    assert result.location.column == 0


def test_syntax_error_offset_zero_falls_back_to_column_0(tmp_path: Path) -> None:
    exc = SyntaxError("invalid syntax")
    exc.lineno = 3
    exc.offset = 0
    result = check_syntax_error(exc, tmp_path / "bad.py", _cfg())
    assert result.location.column == 0


def test_severity_from_config(tmp_path: Path) -> None:
    exc = _syntax_error("def (:\n")
    result = check_syntax_error(exc, tmp_path / "bad.py", _cfg(Severity.WARNING))
    assert result.severity == Severity.WARNING


def test_result_is_not_fixable(tmp_path: Path) -> None:
    exc = _syntax_error("def (:\n")
    result = check_syntax_error(exc, tmp_path / "bad.py", _cfg())
    assert result.fix is None
    assert result.unsafe_fix is None


def test_stub_check_function_returns_empty(tmp_path: Path) -> None:
    func = FunctionInfo(
        name="f",
        file_path=tmp_path / "f.py",
        line=1,
        column=0,
        parameters=(),
        return_annotation=None,
        decorators=(),
        docstring_raw=None,
        docstring_line=0,
        containing_class=None,
        def_start_offset=0,
        def_end_offset=10,
        docstring_start_offset=None,
        docstring_end_offset=None,
    )
    assert check(func, None, _cfg()) == []


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


def test_syntax_error_file_exits_one_text_format(tmp_path: Path) -> None:
    bad = _bad_file(tmp_path)
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(
            main,
            ["check", "--select", "PARSE", str(bad)],
            catch_exceptions=False,
        )
    assert result.exit_code == 1
    assert "PARSE001" in result.output


def test_syntax_error_file_json_format(tmp_path: Path) -> None:
    bad = _bad_file(tmp_path)
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(
            main,
            ["check", "--format", "json", "--select", "PARSE", str(bad)],
            catch_exceptions=False,
        )
    data = json.loads(result.output)
    assert any(d["code"] == "PARSE001" for d in data["diagnostics"])


def test_syntax_error_file_sarif_format(tmp_path: Path) -> None:
    bad = _bad_file(tmp_path)
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(
            main,
            ["check", "--format", "sarif", "--select", "PARSE", str(bad)],
            catch_exceptions=False,
        )
    data = json.loads(result.output)
    rule_ids = [r["ruleId"] for r in data["runs"][0]["results"]]
    assert "PARSE001" in rule_ids


def test_parse001_not_selected_by_doc_select(tmp_path: Path) -> None:
    bad = _bad_file(tmp_path)
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(
            main,
            ["check", "--select", "DOC", "--exit-zero", str(bad)],
            catch_exceptions=False,
        )
    assert "PARSE001" not in result.output


def test_parse001_selected_by_parse_prefix(tmp_path: Path) -> None:
    bad = _bad_file(tmp_path)
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(
            main,
            ["check", "--select", "PARSE", str(bad)],
            catch_exceptions=False,
        )
    assert "PARSE001" in result.output


def test_parse001_severity_off_suppresses(tmp_path: Path) -> None:
    bad = _bad_file(tmp_path)
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        toml = (
            '[project]\nname = "test"\n'
            '[tool.docpact]\nselect = ["PARSE"]\n'
            '[tool.docpact.rules]\nPARSE001 = "off"\n'
        )
        (Path(td) / "pyproject.toml").write_text(toml)
        result = runner.invoke(
            main,
            ["check", "--exit-zero", str(bad)],
            catch_exceptions=False,
        )
    assert "PARSE001" not in result.output


def test_parse001_inline_suppression(tmp_path: Path) -> None:
    # A syntax error on line 1 — put the suppression on line 1 too.
    # parse_suppressions is text-based so it works even on invalid Python.
    bad = tmp_path / "bad.py"
    bad.write_text("def (  # nodo: PARSE001 -- baseline\n")
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(
            main,
            ["check", "--select", "PARSE", "--exit-zero", str(bad)],
            catch_exceptions=False,
        )
    assert "PARSE001" not in result.output

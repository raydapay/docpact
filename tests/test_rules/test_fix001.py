"""Tests for FIX001 — bare # noqa without specific codes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from docpact.model.diagnostic import Severity
from docpact.rules._registry import RuleConfig
from docpact.rules.fix.fix001_bare_noqa import check_bare_noqa
from docpact.suppress import parse_suppressions


def _cfg() -> RuleConfig:
    return RuleConfig(severity=Severity.WARNING, options={})


def _run(source: str, path: Path) -> list:
    sups = parse_suppressions(source)
    return check_bare_noqa(source, sups, path, _cfg())


# ---------------------------------------------------------------------------
# No error cases
# ---------------------------------------------------------------------------


def test_no_noqa_no_error(tmp_path: Path) -> None:
    source = "def foo(): pass\n"
    assert _run(source, tmp_path / "t.py") == []


def test_noqa_with_code_no_error(tmp_path: Path) -> None:
    source = "def foo(): pass  # noqa: DOC001\n"
    assert _run(source, tmp_path / "t.py") == []


def test_noqa_with_multiple_codes_no_error(tmp_path: Path) -> None:
    source = "def foo(): pass  # noqa: DOC001, DOC007\n"
    assert _run(source, tmp_path / "t.py") == []


def test_noqa_with_code_and_reason_no_error(tmp_path: Path) -> None:
    source = "def foo(): pass  # noqa: DOC001 -- legacy code\n"
    assert _run(source, tmp_path / "t.py") == []


# ---------------------------------------------------------------------------
# Bare noqa → FIX001
# ---------------------------------------------------------------------------


def test_bare_noqa_fires(tmp_path: Path) -> None:
    source = "def foo(): pass  # noqa\n"
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1
    assert results[0].code == "FIX001"


def test_bare_noqa_with_spaces_fires(tmp_path: Path) -> None:
    source = "def foo(): pass  #  noqa  \n"
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1
    assert results[0].code == "FIX001"


def test_bare_noqa_line_number_correct(tmp_path: Path) -> None:
    source = "x = 1\ndef foo(): pass  # noqa\n"
    path = tmp_path / "t.py"
    results = _run(source, path)
    assert results[0].location.line == 2


def test_bare_noqa_column_points_to_hash(tmp_path: Path) -> None:
    source = "def foo(): pass  # noqa\n"
    path = tmp_path / "t.py"
    results = _run(source, path)
    col = results[0].location.column
    assert source.splitlines()[0][col] == "#"


def test_multiple_bare_noqa_emits_multiple(tmp_path: Path) -> None:
    source = "x = 1  # noqa\ny = 2  # noqa\n"
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 2


def test_file_path_in_location(tmp_path: Path) -> None:
    path = tmp_path / "t.py"
    source = "x = 1  # noqa\n"
    results = _run(source, path)
    assert results[0].location.file_path == path


def test_severity_from_config(tmp_path: Path) -> None:
    source = "x = 1  # noqa\n"
    sups = parse_suppressions(source)
    cfg = RuleConfig(severity=Severity.ERROR, options={})
    results = check_bare_noqa(source, sups, tmp_path / "t.py", cfg)
    assert results[0].severity == Severity.ERROR


def test_stub_check_function_returns_empty(tmp_path: Path) -> None:
    from docpact.model.function_info import FunctionInfo
    from docpact.rules.fix.fix001_bare_noqa import check

    func = FunctionInfo(
        name="foo",
        file_path=tmp_path / "t.py",
        line=1,
        column=0,
        parameters=(),
        return_annotation=None,
        decorators=(),
        docstring_raw=None,
        docstring_line=1,
        containing_class=None,
        def_start_offset=0,
        def_end_offset=10,
        docstring_start_offset=None,
        docstring_end_offset=None,
    )
    assert check(func, None, _cfg()) == []

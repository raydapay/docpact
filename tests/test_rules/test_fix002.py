"""Tests for FIX002 — suppression names codes but has no -- reason."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from docpact.model.diagnostic import Severity
from docpact.rules._registry import RuleConfig
from docpact.rules.fix.fix002_no_reason import check, check_no_reason
from docpact.suppress import parse_suppressions


def _cfg(severity: Severity = Severity.WARNING) -> RuleConfig:
    return RuleConfig(severity=severity, options={})


def _run(source: str, path: Path, markers: tuple[str, ...] = ("nodo",)) -> list:
    sups = parse_suppressions(source, markers=markers)
    return check_no_reason(source, sups, path, _cfg(), markers=markers)


# ---------------------------------------------------------------------------
# No error cases
# ---------------------------------------------------------------------------


def test_no_suppression_no_error(tmp_path: Path) -> None:
    source = "def foo(): pass\n"
    assert _run(source, tmp_path / "t.py") == []


def test_suppression_with_reason_no_error(tmp_path: Path) -> None:
    source = "def foo(): pass  # nodo: DOC001 -- legacy code\n"
    assert _run(source, tmp_path / "t.py") == []


def test_suppression_with_multi_codes_and_reason_no_error(tmp_path: Path) -> None:
    source = "def foo(): pass  # nodo: DOC001, DOC007 -- pre-docpact legacy\n"
    assert _run(source, tmp_path / "t.py") == []


def test_reason_with_multiple_words_no_error(tmp_path: Path) -> None:
    source = "def foo(): pass  # nodo: DOC001 -- tracked in issue #42\n"
    assert _run(source, tmp_path / "t.py") == []


def test_bare_suppression_not_reported_by_fix002(tmp_path: Path) -> None:
    # Bare suppressions are FIX001's domain, not FIX002's.
    source = "def foo(): pass  # nodo\n"
    assert _run(source, tmp_path / "t.py") == []


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_code_without_reason_fires(tmp_path: Path) -> None:
    source = "def foo(): pass  # nodo: DOC001\n"
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1
    assert results[0].code == "FIX002"


def test_multiple_codes_without_reason_fires(tmp_path: Path) -> None:
    source = "def foo(): pass  # nodo: DOC001, DOC007\n"
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1
    assert results[0].code == "FIX002"


def test_line_number_correct(tmp_path: Path) -> None:
    source = "x = 1\ndef foo(): pass  # nodo: DOC001\n"
    results = _run(source, tmp_path / "t.py")
    assert results[0].location.line == 2


def test_column_points_to_hash(tmp_path: Path) -> None:
    source = "def foo(): pass  # nodo: DOC001\n"
    results = _run(source, tmp_path / "t.py")
    col = results[0].location.column
    assert source.splitlines()[0][col] == "#"


def test_file_path_in_location(tmp_path: Path) -> None:
    path = tmp_path / "t.py"
    source = "def foo(): pass  # nodo: DOC001\n"
    results = _run(source, path)
    assert results[0].location.file_path == path


def test_multiple_lines_each_emit(tmp_path: Path) -> None:
    source = "x = 1  # nodo: DOC001\ny = 2  # nodo: DOC007\n"
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 2


def test_mix_of_reason_and_no_reason(tmp_path: Path) -> None:
    source = "x = 1  # nodo: DOC001 -- tracked\ny = 2  # nodo: DOC007\n"
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1
    assert results[0].location.line == 2


def test_severity_from_config(tmp_path: Path) -> None:
    source = "x = 1  # nodo: DOC001\n"
    sups = parse_suppressions(source)
    cfg = RuleConfig(severity=Severity.ERROR, options={})
    results = check_no_reason(source, sups, tmp_path / "t.py", cfg)
    assert results[0].severity == Severity.ERROR


def test_default_severity_is_warning(tmp_path: Path) -> None:
    source = "x = 1  # nodo: DOC001\n"
    results = _run(source, tmp_path / "t.py")
    assert results[0].severity == Severity.WARNING


def test_custom_marker(tmp_path: Path) -> None:
    source = "x = 1  # noqa: DOC001\n"
    results = _run(source, tmp_path / "t.py", markers=("noqa",))
    assert len(results) == 1
    assert results[0].code == "FIX002"


def test_custom_marker_with_reason_no_error(tmp_path: Path) -> None:
    source = "x = 1  # noqa: DOC001 -- reason\n"
    results = _run(source, tmp_path / "t.py", markers=("noqa",))
    assert results == []


# ---------------------------------------------------------------------------
# Stub check() function
# ---------------------------------------------------------------------------


def test_stub_check_function_returns_empty(tmp_path: Path) -> None:
    from docpact.model.function_info import FunctionInfo

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

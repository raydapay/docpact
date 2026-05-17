"""Tests for DOC099 — [FILL] placeholder marker not replaced."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from docpact.model.diagnostic import Severity
from docpact.model.function_info import FunctionInfo
from docpact.model.parsed_docstring import ParsedDocstring
from docpact.rules._registry import RuleConfig
from docpact.rules.doc.doc099_fill_marker import check


def _func(path: Path) -> FunctionInfo:
    return FunctionInfo(
        name="foo",
        file_path=path,
        line=1,
        column=0,
        parameters=(),
        return_annotation=None,
        decorators=(),
        docstring_raw='"""Summary."""',
        docstring_line=2,
        containing_class=None,
        def_start_offset=0,
        def_end_offset=20,
        docstring_start_offset=20,
        docstring_end_offset=35,
    )


def _doc(raw: str) -> ParsedDocstring:
    return ParsedDocstring(summary="Summary.", description=None, sections={}, raw=raw)


def _cfg() -> RuleConfig:
    return RuleConfig(severity=Severity.ERROR, options={})


def test_no_fill_no_diagnostic(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    doc = _doc("Summary. No placeholders here.")
    assert check(func, doc, _cfg()) == []


def test_fill_marker_in_summary_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    doc = _doc("[FILL: single-sentence summary in imperative mood]")
    results = check(func, doc, _cfg())
    assert len(results) == 1
    assert results[0].code == "DOC099"
    assert "FILL" in results[0].message


def test_fill_marker_in_section_body_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    raw = "Summary.\n\nArgs:\n    x: [FILL]"
    doc = _doc(raw)
    results = check(func, doc, _cfg())
    assert len(results) == 1
    assert results[0].code == "DOC099"


def test_fill_partial_word_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    doc = _doc("[FILL: describe the return value]")
    results = check(func, doc, _cfg())
    assert len(results) == 1


def test_no_docstring_returns_empty(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    assert check(func, None, _cfg()) == []


def test_location_points_to_function_definition(tmp_path: Path) -> None:
    path = tmp_path / "t.py"
    func = _func(path)
    doc = _doc("[FILL: summary]")
    results = check(func, doc, _cfg())
    assert results[0].location.file_path == path
    assert results[0].location.line == 1
    assert results[0].location.column == 0


def test_severity_respected(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    doc = _doc("[FILL]")
    cfg = RuleConfig(severity=Severity.WARNING, options={})
    results = check(func, doc, cfg)
    assert results[0].severity == Severity.WARNING


def test_no_fix_available(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    doc = _doc("[FILL]")
    results = check(func, doc, _cfg())
    assert results[0].fix is None
    assert results[0].unsafe_fix is None

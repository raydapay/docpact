"""Tests for DOC014 — suspected parameter name typo."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from docpact.model.diagnostic import Severity
from docpact.model.function_info import FunctionInfo, ParameterInfo
from docpact.model.parsed_docstring import ParsedDocstring, Section, SectionEntry
from docpact.rules._registry import RuleConfig
from docpact.rules.doc.doc014_suspicious_param import check


def _param(name: str, kind: str = "positional") -> ParameterInfo:
    return ParameterInfo(name=name, annotation=None, default=None, kind=kind)


def _func(path: Path, params: tuple[ParameterInfo, ...] = ()) -> FunctionInfo:
    return FunctionInfo(
        name="foo",
        file_path=path,
        line=1,
        column=0,
        parameters=params,
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


def _doc(documented: dict[str, str]) -> ParsedDocstring:
    entries = tuple(SectionEntry(key=k, description=v) for k, v in documented.items())
    sections: dict[str, Section] = (
        {"Args": Section(name="Args", entries=entries)} if entries else {}
    )
    return ParsedDocstring(summary="Summary.", description=None, sections=sections, raw="Summary.")


def _cfg() -> RuleConfig:
    return RuleConfig(severity=Severity.WARNING, options={})


# ---------------------------------------------------------------------------
# No error cases
# ---------------------------------------------------------------------------


def test_exact_match_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("query"),))
    doc = _doc({"query": "The search query."})
    assert check(func, doc, _cfg()) == []


def test_no_docstring_returns_empty(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x"),))
    assert check(func, None, _cfg()) == []


def test_no_args_section_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x"),))
    doc = ParsedDocstring(summary="S.", description=None, sections={}, raw="S.")
    assert check(func, doc, _cfg()) == []


def test_totally_different_name_no_suggestion(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("query"),))
    doc = _doc({"zzz": "Unrelated."})
    results = check(func, doc, _cfg())
    assert results == []


# ---------------------------------------------------------------------------
# Typo detected → DOC014 fires
# ---------------------------------------------------------------------------


def test_one_char_difference_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("query"),))
    doc = _doc({"qeury": "Desc."})
    results = check(func, doc, _cfg())
    assert len(results) == 1
    assert results[0].code == "DOC014"
    assert "query" in results[0].message
    assert "qeury" in results[0].message


def test_missing_char_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("token"),))
    doc = _doc({"tken": "Desc."})
    results = check(func, doc, _cfg())
    assert len(results) == 1


def test_extra_char_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("limit"),))
    doc = _doc({"limitt": "Desc."})
    results = check(func, doc, _cfg())
    assert len(results) == 1


def test_multiple_typos_emits_multiple(tmp_path: Path) -> None:
    func = _func(
        tmp_path / "t.py",
        params=(_param("query"), _param("limit")),
    )
    doc = _doc({"qeury": "Desc.", "limt": "Desc."})
    results = check(func, doc, _cfg())
    assert len(results) == 2


def test_severity_is_warning(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("query"),))
    doc = _doc({"qeury": "Desc."})
    results = check(func, doc, _cfg())
    assert results[0].severity == Severity.WARNING


def test_no_fix_available(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("query"),))
    doc = _doc({"qeury": "Desc."})
    results = check(func, doc, _cfg())
    assert results[0].fix is None
    assert results[0].unsafe_fix is None


def test_bound_param_excluded_from_valid_set(tmp_path: Path) -> None:
    params = (_param("self", kind="bound"), _param("query"))
    func = _func(tmp_path / "t.py", params=params)
    doc = _doc({"self": "Desc."})
    # "self" is documented but is a bound param — not a typo of "query" (too different)
    results = check(func, doc, _cfg())
    assert results == []

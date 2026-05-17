"""Tests for DOC051 — Constraints section duplicates Annotated metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from docpact.model.diagnostic import Severity
from docpact.model.function_info import FunctionInfo, ParameterInfo
from docpact.model.parsed_docstring import ParsedDocstring, Section
from docpact.rules._registry import RuleConfig
from docpact.rules.doc.doc051_annotated_constraint import check


def _param(name: str, annotation: str | None = None) -> ParameterInfo:
    return ParameterInfo(name=name, annotation=annotation, default=None, kind="positional")


def _func(path: Path, params: tuple[ParameterInfo, ...] = ()) -> FunctionInfo:
    return FunctionInfo(
        name="search",
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


def _doc(constraints_body: str | None = None) -> ParsedDocstring:
    sections: dict[str, Section] = {}
    if constraints_body is not None:
        sections["Constraints"] = Section(name="Constraints", body=constraints_body)
    return ParsedDocstring(summary="Summary.", description=None, sections=sections, raw="Summary.")


def _cfg() -> RuleConfig:
    return RuleConfig(severity=Severity.ERROR, options={})


# ---------------------------------------------------------------------------
# No error cases
# ---------------------------------------------------------------------------


def test_no_docstring_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    assert check(func, None, _cfg()) == []


def test_no_constraints_section_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("q", "Annotated[str, MaxLen(100)]"),))
    assert check(func, _doc(None), _cfg()) == []


def test_no_annotated_in_params_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("q", "str"),))
    doc = _doc("max length 100")
    assert check(func, doc, _cfg()) == []


def test_annotated_without_numeric_constraint_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("q", "Annotated[str, Field(default='')]"),))
    doc = _doc("Must be non-empty.")
    assert check(func, doc, _cfg()) == []


def test_constraints_is_none_dot_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("q", "Annotated[str, MaxLen(100)]"),))
    doc = _doc("None.")
    assert check(func, doc, _cfg()) == []


def test_value_in_annotation_not_in_constraints_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("q", "Annotated[str, MaxLen(4096)]"),))
    doc = _doc("Must be a valid search term.")
    assert check(func, doc, _cfg()) == []


# ---------------------------------------------------------------------------
# Duplication detected → DOC051 fires
# ---------------------------------------------------------------------------


def test_maxlen_duplicated_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("q", "Annotated[str, MaxLen(4096)]"),))
    doc = _doc("max length 4096 characters")
    results = check(func, doc, _cfg())
    assert len(results) == 1
    assert results[0].code == "DOC051"
    assert "MaxLen(4096)" in results[0].message


def test_ge_constraint_duplicated_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("n", "Annotated[int, Ge(0)]"),))
    doc = _doc("must be at least 0")
    results = check(func, doc, _cfg())
    assert len(results) == 1
    assert results[0].code == "DOC051"


def test_le_constraint_duplicated_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("n", "Annotated[int, Le(100)]"),))
    doc = _doc("must be at most 100")
    results = check(func, doc, _cfg())
    assert len(results) == 1


def test_minlen_duplicated_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("s", "Annotated[str, MinLen(1)]"),))
    doc = _doc("minimum length 1")
    results = check(func, doc, _cfg())
    assert len(results) == 1


def test_max_length_kwarg_form_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("s", "Annotated[str, Field(max_length=256)]"),))
    doc = _doc("max 256 chars")
    results = check(func, doc, _cfg())
    assert len(results) == 1


def test_no_duplicate_different_param_no_error(tmp_path: Path) -> None:
    params = (
        _param("q", "Annotated[str, MaxLen(4096)]"),
        _param("n", "int"),
    )
    func = _func(tmp_path / "t.py", params=params)
    doc = _doc("Must be a valid term.")
    assert check(func, doc, _cfg()) == []


def test_error_severity(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("q", "Annotated[str, MaxLen(4096)]"),))
    doc = _doc("max length 4096")
    results = check(func, doc, _cfg())
    assert results[0].severity == Severity.ERROR

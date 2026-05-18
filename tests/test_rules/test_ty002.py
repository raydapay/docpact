"""Tests for TY002 — Returns section is 'None.' but return annotation is non-None."""

from __future__ import annotations

from pathlib import Path

from docpact.model.diagnostic import Severity
from docpact.model.function_info import FunctionInfo
from docpact.model.parsed_docstring import ParsedDocstring, Section
from docpact.rules._registry import RuleConfig
from docpact.rules.ty.ty002_nonnone_return_empty import check

_PATH = Path("test.py")
_CFG = RuleConfig(severity=Severity.WARNING, options={})


def _func(return_annotation: str | None = None) -> FunctionInfo:
    return FunctionInfo(
        name="foo",
        file_path=_PATH,
        line=1,
        column=0,
        parameters=(),
        return_annotation=return_annotation,
        decorators=(),
        docstring_raw='"""Summary."""',
        docstring_line=2,
        containing_class=None,
        def_start_offset=0,
        def_end_offset=20,
        docstring_start_offset=20,
        docstring_end_offset=35,
    )


def _doc(returns_body: str | None = None) -> ParsedDocstring:
    sections: dict[str, Section] = {}
    if returns_body is not None:
        sections["Returns"] = Section(name="Returns", body=returns_body)
    return ParsedDocstring(summary="Summary.", description=None, sections=sections, raw="Summary.")


# ---------------------------------------------------------------------------
# Positive cases — TY002 fires
# ---------------------------------------------------------------------------


def test_fires_on_int_annotation_with_none_body() -> None:
    func = _func(return_annotation="int")
    doc = _doc(returns_body="None.")
    results = check(func, doc, _CFG)
    assert len(results) == 1
    assert results[0].code == "TY002"


def test_fires_on_complex_annotation() -> None:
    func = _func(return_annotation="dict[str, int]")
    doc = _doc(returns_body="None.")
    results = check(func, doc, _CFG)
    assert len(results) == 1


def test_fires_on_optional_annotation() -> None:
    func = _func(return_annotation="User | None")
    doc = _doc(returns_body="None.")
    results = check(func, doc, _CFG)
    assert len(results) == 1


def test_message_includes_annotation() -> None:
    func = _func(return_annotation="list[str]")
    doc = _doc(returns_body="None.")
    result = check(func, doc, _CFG)[0]
    assert "list[str]" in result.message
    assert "None." in result.message


def test_severity_uses_config() -> None:
    func = _func(return_annotation="int")
    doc = _doc(returns_body="None.")
    cfg = RuleConfig(severity=Severity.ERROR, options={})
    result = check(func, doc, cfg)[0]
    assert result.severity == Severity.ERROR


def test_location_is_func_line() -> None:
    func = _func(return_annotation="int")
    doc = _doc(returns_body="None.")
    result = check(func, doc, _CFG)[0]
    assert result.location.file_path == _PATH
    assert result.location.line == 1


# ---------------------------------------------------------------------------
# Negative cases — TY002 does not fire
# ---------------------------------------------------------------------------


def test_no_fire_when_no_docstring() -> None:
    assert check(_func(return_annotation="int"), None, _CFG) == []


def test_no_fire_when_no_returns_section() -> None:
    doc = _doc()
    assert check(_func(return_annotation="int"), doc, _CFG) == []


def test_no_fire_when_annotation_is_none() -> None:
    func = _func(return_annotation="None")
    doc = _doc(returns_body="None.")
    assert check(func, doc, _CFG) == []


def test_no_fire_when_unannotated() -> None:
    func = _func(return_annotation=None)
    doc = _doc(returns_body="None.")
    assert check(func, doc, _CFG) == []


def test_no_fire_when_returns_has_content() -> None:
    func = _func(return_annotation="int")
    doc = _doc(returns_body="The count of processed items.")
    assert check(func, doc, _CFG) == []


def test_no_fire_when_returns_body_is_none_without_period() -> None:
    # Only the canonical "None." triggers TY002; other empty forms don't.
    func = _func(return_annotation="int")
    doc = _doc(returns_body="None")
    assert check(func, doc, _CFG) == []


def test_no_fire_when_returns_body_is_none_object() -> None:
    func = _func(return_annotation="int")
    doc = _doc(returns_body=None)
    assert check(func, doc, _CFG) == []


def test_no_fire_on_empty_string_annotation() -> None:
    func = _func(return_annotation="")
    doc = _doc(returns_body="None.")
    assert check(func, doc, _CFG) == []

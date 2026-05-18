"""Tests for TY001 — Returns section present but return annotation is None."""

from __future__ import annotations

from pathlib import Path

from docpact.model.diagnostic import Severity
from docpact.model.function_info import FunctionInfo
from docpact.parser.docstring import GoogleParser
from docpact.rules._registry import RuleConfig
from docpact.rules.ty.ty001_none_return_with_returns import check

_PARSER = GoogleParser()
_PATH = Path("test.py")
_CFG = RuleConfig(severity=Severity.ERROR, options={})


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


def _parse(raw: str):  # nodo: DOC001 -- test helper, signature is self-evident
    return _PARSER.parse(raw)


# ---------------------------------------------------------------------------
# Positive cases — TY001 fires
# ---------------------------------------------------------------------------


def test_fires_on_none_annotation_with_content() -> None:
    func = _func(return_annotation="None")
    doc = _parse("Do something.\n\nReturns:\n    The processed result.\n")
    results = check(func, doc, _CFG)
    assert len(results) == 1
    assert results[0].code == "TY001"


def test_fires_on_multiline_returns_body() -> None:
    func = _func(return_annotation="None")
    doc = _parse(
        "Do something.\n\nReturns:\n    A dict mapping keys to values.\n    May be empty.\n"
    )
    results = check(func, doc, _CFG)
    assert len(results) == 1


def test_fires_on_typed_returns_entry() -> None:
    func = _func(return_annotation="None")
    doc = _parse("Do something.\n\nReturns:\n    int: The count of processed items.\n")
    results = check(func, doc, _CFG)
    assert len(results) == 1


def test_message_mentions_none_and_returns() -> None:
    func = _func(return_annotation="None")
    doc = _parse("Do something.\n\nReturns:\n    The result.\n")
    result = check(func, doc, _CFG)[0]
    assert "None" in result.message
    assert "Returns" in result.message


def test_severity_uses_config() -> None:
    func = _func(return_annotation="None")
    doc = _parse("Do something.\n\nReturns:\n    The result.\n")
    cfg = RuleConfig(severity=Severity.WARNING, options={})
    result = check(func, doc, cfg)[0]
    assert result.severity == Severity.WARNING


def test_location_is_func_line() -> None:
    func = _func(return_annotation="None")
    doc = _parse("Do something.\n\nReturns:\n    The result.\n")
    result = check(func, doc, _CFG)[0]
    assert result.location.file_path == _PATH
    assert result.location.line == 1


# ---------------------------------------------------------------------------
# Negative cases — TY001 does not fire
# ---------------------------------------------------------------------------


def test_no_fire_when_no_docstring() -> None:
    assert check(_func(return_annotation="None"), None, _CFG) == []


def test_no_fire_when_no_returns_section() -> None:
    doc = _parse("Do something.")
    assert check(_func(return_annotation="None"), doc, _CFG) == []


def test_no_fire_when_annotation_is_non_none() -> None:
    func = _func(return_annotation="int")
    doc = _parse("Do something.\n\nReturns:\n    The result.\n")
    assert check(func, doc, _CFG) == []


def test_no_fire_when_unannotated() -> None:
    func = _func(return_annotation=None)
    doc = _parse("Do something.\n\nReturns:\n    The result.\n")
    assert check(func, doc, _CFG) == []


def test_no_fire_on_canonical_empty_returns() -> None:
    func = _func(return_annotation="None")
    doc = _parse("Do something.\n\nReturns:\n    None.\n")
    assert check(func, doc, _CFG) == []


def test_no_fire_on_returns_body_none_without_period() -> None:
    func = _func(return_annotation="None")
    doc = _parse("Do something.\n\nReturns:\n    None\n")
    assert check(func, doc, _CFG) == []


def test_no_fire_on_returns_body_na() -> None:
    func = _func(return_annotation="None")
    doc = _parse("Do something.\n\nReturns:\n    N/A\n")
    assert check(func, doc, _CFG) == []


def test_no_fire_on_optional_return_type() -> None:
    func = _func(return_annotation="int | None")
    doc = _parse("Do something.\n\nReturns:\n    The result, or None on failure.\n")
    assert check(func, doc, _CFG) == []

"""Tests for MCP001 — both decorator description= and docstring MCP: section present."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from docpact.model.diagnostic import Severity
from docpact.model.function_info import DecoratorInfo, FunctionInfo
from docpact.model.parsed_docstring import ParsedDocstring, Section
from docpact.rules._registry import RuleConfig
from docpact.rules.mcp.mcp001_decorator_docstring_conflict import check


def _func(path: Path, decorators: tuple[DecoratorInfo, ...] = ()) -> FunctionInfo:
    return FunctionInfo(
        name="search",
        file_path=path,
        line=5,
        column=0,
        parameters=(),
        return_annotation=None,
        decorators=decorators,
        docstring_raw='"""Summary."""',
        docstring_line=6,
        containing_class=None,
        def_start_offset=0,
        def_end_offset=30,
        docstring_start_offset=30,
        docstring_end_offset=45,
    )


def _doc(has_mcp_section: bool = False, mcp_body: str = "A search tool.") -> ParsedDocstring:
    sections: dict[str, Section] = {}
    if has_mcp_section:
        sections["MCP"] = Section(name="MCP", body=mcp_body)
    return ParsedDocstring(summary="Summary.", description=None, sections=sections, raw="Summary.")


def _cfg() -> RuleConfig:
    return RuleConfig(severity=Severity.ERROR, options={})


# ---------------------------------------------------------------------------
# No conflict → no diagnostic
# ---------------------------------------------------------------------------


def test_no_docstring_returns_empty(tmp_path: Path) -> None:
    dec = (DecoratorInfo(name="mcp.tool", arguments={"description": '"A search tool."'}),)
    func = _func(tmp_path / "t.py", decorators=dec)
    assert check(func, None, _cfg()) == []


def test_only_mcp_section_no_decorator_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    doc = _doc(has_mcp_section=True)
    assert check(func, doc, _cfg()) == []


def test_only_decorator_description_no_mcp_section_no_error(tmp_path: Path) -> None:
    dec = (DecoratorInfo(name="mcp.tool", arguments={"description": '"A search tool."'}),)
    func = _func(tmp_path / "t.py", decorators=dec)
    doc = _doc(has_mcp_section=False)
    assert check(func, doc, _cfg()) == []


def test_decorator_without_description_kwarg_no_error(tmp_path: Path) -> None:
    dec = (DecoratorInfo(name="mcp.tool", arguments={"name": '"search"'}),)
    func = _func(tmp_path / "t.py", decorators=dec)
    doc = _doc(has_mcp_section=True)
    assert check(func, doc, _cfg()) == []


def test_non_mcp_decorator_with_description_no_error(tmp_path: Path) -> None:
    dec = (DecoratorInfo(name="app.get", arguments={"description": '"path"'}),)
    func = _func(tmp_path / "t.py", decorators=dec)
    doc = _doc(has_mcp_section=True)
    # app.get is not an MCP decorator → no MCP001
    assert check(func, doc, _cfg()) == []


# ---------------------------------------------------------------------------
# Both present → MCP001 fires
# ---------------------------------------------------------------------------


def test_mcp_tool_and_mcp_section_fires(tmp_path: Path) -> None:
    dec = (DecoratorInfo(name="mcp.tool", arguments={"description": '"A search tool."'}),)
    func = _func(tmp_path / "t.py", decorators=dec)
    doc = _doc(has_mcp_section=True)
    results = check(func, doc, _cfg())
    assert len(results) == 1
    assert results[0].code == "MCP001"


def test_mcp_resource_and_mcp_section_fires(tmp_path: Path) -> None:
    dec = (DecoratorInfo(name="mcp.resource", arguments={"description": '"A resource."'}),)
    func = _func(tmp_path / "t.py", decorators=dec)
    doc = _doc(has_mcp_section=True)
    results = check(func, doc, _cfg())
    assert len(results) == 1
    assert results[0].code == "MCP001"


def test_unqualified_tool_decorator_fires(tmp_path: Path) -> None:
    dec = (DecoratorInfo(name="tool", arguments={"description": '"A tool."'}),)
    func = _func(tmp_path / "t.py", decorators=dec)
    doc = _doc(has_mcp_section=True)
    results = check(func, doc, _cfg())
    assert len(results) == 1


def test_location_is_function_definition(tmp_path: Path) -> None:
    path = tmp_path / "t.py"
    dec = (DecoratorInfo(name="mcp.tool", arguments={"description": '"A search tool."'}),)
    func = _func(path, decorators=dec)
    doc = _doc(has_mcp_section=True)
    results = check(func, doc, _cfg())
    assert results[0].location.file_path == path
    assert results[0].location.line == 5


def test_severity_follows_config(tmp_path: Path) -> None:
    dec = (DecoratorInfo(name="mcp.tool", arguments={"description": '"desc"'}),)
    func = _func(tmp_path / "t.py", decorators=dec)
    doc = _doc(has_mcp_section=True)
    results = check(func, doc, _cfg())
    assert results[0].severity == Severity.ERROR  # _cfg() overrides to ERROR


def test_default_severity_is_warning() -> None:
    from docpact.rules._registry import all_rules

    meta, _ = all_rules()["MCP001"]
    assert meta.default_severity == Severity.WARNING


def test_first_matching_decorator_wins(tmp_path: Path) -> None:
    dec = (
        DecoratorInfo(name="staticmethod", arguments={}),
        DecoratorInfo(name="mcp.tool", arguments={"description": '"desc"'}),
    )
    func = _func(tmp_path / "t.py", decorators=dec)
    doc = _doc(has_mcp_section=True)
    results = check(func, doc, _cfg())
    assert len(results) == 1

"""Tests for DOC012 — required docstring section missing for function tier."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from docpact.model.diagnostic import Severity
from docpact.model.function_info import DecoratorInfo, FunctionInfo, ParameterInfo
from docpact.model.parsed_docstring import ParsedDocstring, Section, SectionEntry
from docpact.rules._registry import RuleConfig
from docpact.rules.doc.doc012_missing_section import check


def _param(name: str, kind: str = "positional", annotation: str | None = None) -> ParameterInfo:
    return ParameterInfo(name=name, annotation=annotation, default=None, kind=kind)


def _func(
    path: Path,
    params: tuple[ParameterInfo, ...] = (),
    return_annotation: str | None = None,
    decorators: tuple[DecoratorInfo, ...] = (),
) -> FunctionInfo:
    return FunctionInfo(
        name="foo",
        file_path=path,
        line=1,
        column=0,
        parameters=params,
        return_annotation=return_annotation,
        decorators=decorators,
        docstring_raw='"""Summary."""',
        docstring_line=2,
        containing_class=None,
        def_start_offset=0,
        def_end_offset=20,
        docstring_start_offset=20,
        docstring_end_offset=35,
    )


def _doc(sections: dict[str, Section] | None = None) -> ParsedDocstring:
    return ParsedDocstring(
        summary="Summary.",
        description=None,
        sections=sections or {},
        raw="Summary.",
    )


def _cfg(tier: int = 2) -> RuleConfig:
    return RuleConfig(severity=Severity.ERROR, options={"tier": tier})


def _section(name: str, body: str = "content") -> Section:
    return Section(name=name, body=body)


# ---------------------------------------------------------------------------
# No docstring → no DOC012 (DOC001's domain)
# ---------------------------------------------------------------------------


def test_no_docstring_returns_empty(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x"),))
    assert check(func, None, _cfg()) == []


# ---------------------------------------------------------------------------
# Tier 1: no section requirements
# ---------------------------------------------------------------------------


def test_tier1_no_params_no_sections_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x"),))
    assert check(func, _doc(), _cfg(tier=1)) == []


def test_tier1_missing_args_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x"),))
    assert check(func, _doc(), _cfg(tier=1)) == []


# ---------------------------------------------------------------------------
# Tier 2: Args and Returns requirements
# ---------------------------------------------------------------------------


def test_tier2_has_params_missing_args_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x"),))
    results = check(func, _doc(), _cfg(tier=2))
    codes = [r.code for r in results]
    assert "DOC012" in codes
    assert any("Args" in r.message for r in results)


def test_tier2_has_params_and_args_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x"),))
    sections = {"Args": Section(name="Args", entries=(SectionEntry(key="x", description="desc"),))}
    assert check(func, _doc(sections), _cfg(tier=2)) == []


def test_tier2_no_params_missing_args_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=())
    assert check(func, _doc(), _cfg(tier=2)) == []


def test_tier2_bound_only_missing_args_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("self", kind="bound"),))
    assert check(func, _doc(), _cfg(tier=2)) == []


def test_tier2_non_none_return_missing_returns_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", return_annotation="str")
    results = check(func, _doc(), _cfg(tier=2))
    assert any("Returns" in r.message for r in results)


def test_tier2_non_none_return_has_returns_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", return_annotation="str")
    sections = {"Returns": _section("Returns", "A string.")}
    assert check(func, _doc(sections), _cfg(tier=2)) == []


def test_tier2_none_return_annotation_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", return_annotation="None")
    assert check(func, _doc(), _cfg(tier=2)) == []


def test_tier2_empty_return_annotation_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", return_annotation=None)
    assert check(func, _doc(), _cfg(tier=2)) == []


# ---------------------------------------------------------------------------
# Tier 3: Raises, Constraints, Stability, MCP
# ---------------------------------------------------------------------------


def test_tier3_missing_raises_fires(tmp_path: Path) -> None:
    sections = {
        "Constraints": _section("Constraints"),
        "Stability": _section("Stability", "stable"),
        "MCP": _section("MCP"),
    }
    func = _func(tmp_path / "t.py")
    results = check(func, _doc(sections), _cfg(tier=3))
    assert any("Raises" in r.message for r in results)


def test_tier3_missing_constraints_fires(tmp_path: Path) -> None:
    sections = {
        "Raises": Section(name="Raises", body="None."),
        "Stability": _section("Stability", "stable"),
        "MCP": _section("MCP"),
    }
    func = _func(tmp_path / "t.py")
    results = check(func, _doc(sections), _cfg(tier=3))
    assert any("Constraints" in r.message for r in results)


def test_tier3_missing_stability_fires(tmp_path: Path) -> None:
    sections = {
        "Raises": Section(name="Raises", body="None."),
        "Constraints": _section("Constraints", "None."),
        "MCP": _section("MCP"),
    }
    func = _func(tmp_path / "t.py")
    results = check(func, _doc(sections), _cfg(tier=3))
    assert any("Stability" in r.message for r in results)


def test_tier3_missing_mcp_section_and_no_decorator_fires(tmp_path: Path) -> None:
    sections = {
        "Raises": Section(name="Raises", body="None."),
        "Constraints": _section("Constraints", "None."),
        "Stability": _section("Stability", "stable"),
    }
    func = _func(tmp_path / "t.py")
    results = check(func, _doc(sections), _cfg(tier=3))
    assert any("MCP" in r.message for r in results)


def test_tier3_missing_mcp_but_has_decorator_description_no_error(tmp_path: Path) -> None:
    sections = {
        "Raises": Section(name="Raises", body="None."),
        "Constraints": _section("Constraints", "None."),
        "Stability": _section("Stability", "stable"),
    }
    decorators = (DecoratorInfo(name="mcp.tool", arguments={"description": '"Search docs"'}),)
    func = _func(tmp_path / "t.py", decorators=decorators)
    results = check(func, _doc(sections), _cfg(tier=3))
    assert not any("MCP" in r.message for r in results)


def test_tier3_all_sections_present_no_error(tmp_path: Path) -> None:
    sections = {
        "Raises": Section(name="Raises", body="None."),
        "Constraints": _section("Constraints", "None."),
        "Stability": _section("Stability", "stable"),
        "MCP": _section("MCP", "A search tool."),
    }
    func = _func(tmp_path / "t.py")
    assert check(func, _doc(sections), _cfg(tier=3)) == []


def test_tier3_canonical_none_section_satisfies_requirement(tmp_path: Path) -> None:
    sections = {
        "Raises": Section(name="Raises", body="None."),
        "Constraints": Section(name="Constraints", body="None."),
        "Stability": _section("Stability", "stable"),
        "MCP": _section("MCP"),
    }
    func = _func(tmp_path / "t.py")
    assert check(func, _doc(sections), _cfg(tier=3)) == []


def test_multiple_missing_sections_emits_multiple_results(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x"),))
    results = check(func, _doc(), _cfg(tier=3))
    # At tier 3 with no sections and params: Args, Raises, Constraints, Stability, MCP
    assert len(results) >= 3

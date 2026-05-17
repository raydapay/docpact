"""Tests for DOC013 — empty section uses non-canonical form."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from docpact.model.diagnostic import Severity
from docpact.model.function_info import FunctionInfo
from docpact.model.parsed_docstring import ParsedDocstring, Section, SectionEntry
from docpact.rules._registry import RuleConfig
from docpact.rules.doc.doc013_noncanonical_empty import check


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


def _doc(sections: dict[str, Section]) -> ParsedDocstring:
    return ParsedDocstring(summary="Summary.", description=None, sections=sections, raw="Summary.")


def _cfg() -> RuleConfig:
    return RuleConfig(severity=Severity.WARNING, options={})


# ---------------------------------------------------------------------------
# Canonical form passes
# ---------------------------------------------------------------------------


def test_canonical_none_dot_passes(tmp_path: Path) -> None:
    sections = {"Raises": Section(name="Raises", body="None.")}
    assert check(_func(tmp_path / "t.py"), _doc(sections), _cfg()) == []


def test_section_with_real_entries_passes(tmp_path: Path) -> None:
    entries = (SectionEntry(key="ValueError", description="Bad input."),)
    sections = {"Raises": Section(name="Raises", entries=entries)}
    assert check(_func(tmp_path / "t.py"), _doc(sections), _cfg()) == []


def test_section_with_real_body_passes(tmp_path: Path) -> None:
    sections = {"Constraints": Section(name="Constraints", body="Must be positive.")}
    assert check(_func(tmp_path / "t.py"), _doc(sections), _cfg()) == []


def test_no_sections_no_error(tmp_path: Path) -> None:
    assert check(_func(tmp_path / "t.py"), _doc({}), _cfg()) == []


def test_no_docstring_returns_empty(tmp_path: Path) -> None:
    assert check(_func(tmp_path / "t.py"), None, _cfg()) == []


# ---------------------------------------------------------------------------
# Non-canonical empty forms fire
# ---------------------------------------------------------------------------


def test_body_na_fires(tmp_path: Path) -> None:
    sections = {"Raises": Section(name="Raises", body="N/A")}
    results = check(_func(tmp_path / "t.py"), _doc(sections), _cfg())
    assert len(results) == 1
    assert results[0].code == "DOC013"
    assert "Raises" in results[0].message


def test_body_na_lowercase_fires(tmp_path: Path) -> None:
    sections = {"Constraints": Section(name="Constraints", body="n/a")}
    results = check(_func(tmp_path / "t.py"), _doc(sections), _cfg())
    assert len(results) == 1


def test_body_na_no_slash_fires(tmp_path: Path) -> None:
    sections = {"Raises": Section(name="Raises", body="NA")}
    results = check(_func(tmp_path / "t.py"), _doc(sections), _cfg())
    assert len(results) == 1


def test_body_none_without_period_fires(tmp_path: Path) -> None:
    sections = {"Raises": Section(name="Raises", body="None")}
    results = check(_func(tmp_path / "t.py"), _doc(sections), _cfg())
    assert len(results) == 1
    assert results[0].code == "DOC013"


def test_body_empty_string_fires(tmp_path: Path) -> None:
    sections = {"Raises": Section(name="Raises", body="")}
    results = check(_func(tmp_path / "t.py"), _doc(sections), _cfg())
    assert len(results) == 1


def test_body_none_value_fires(tmp_path: Path) -> None:
    sections = {"Raises": Section(name="Raises", body=None)}
    results = check(_func(tmp_path / "t.py"), _doc(sections), _cfg())
    assert len(results) == 1


def test_multiple_bad_sections_emits_multiple_results(tmp_path: Path) -> None:
    sections = {
        "Raises": Section(name="Raises", body="N/A"),
        "Constraints": Section(name="Constraints", body="None"),
    }
    results = check(_func(tmp_path / "t.py"), _doc(sections), _cfg())
    assert len(results) == 2


def test_severity_is_warning_by_default(tmp_path: Path) -> None:
    sections = {"Raises": Section(name="Raises", body="N/A")}
    results = check(_func(tmp_path / "t.py"), _doc(sections), _cfg())
    assert results[0].severity == Severity.WARNING


def test_section_body_whitespace_only_fires(tmp_path: Path) -> None:
    sections = {"Raises": Section(name="Raises", body="   ")}
    results = check(_func(tmp_path / "t.py"), _doc(sections), _cfg())
    assert len(results) == 1

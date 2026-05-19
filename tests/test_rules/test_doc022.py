"""Tests for DOC022 — typed prose annotation doesn't match signature type."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from docpact.model.diagnostic import Severity
from docpact.model.function_info import FunctionInfo, ParameterInfo
from docpact.model.parsed_docstring import ParsedDocstring, Section, SectionEntry
from docpact.rules._registry import RuleConfig
from docpact.rules.doc.doc022_type_prose_mismatch import check


def _param(
    name: str,
    annotation: str | None = None,
    kind: str = "positional",
) -> ParameterInfo:
    return ParameterInfo(name=name, annotation=annotation, default=None, kind=kind)


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


def _entry(name: str, type_annotation: str | None, description: str = "desc") -> SectionEntry:
    return SectionEntry(key=name, description=description, type_annotation=type_annotation)


def _doc(entries: list[SectionEntry]) -> ParsedDocstring:
    section = Section(name="Args", entries=tuple(entries))
    return ParsedDocstring(
        summary="Summary.",
        description=None,
        sections={"Args": section},
        raw="Summary.",
    )


def _cfg() -> RuleConfig:
    return RuleConfig(severity=Severity.WARNING, options={})


# ---------------------------------------------------------------------------
# Silent cases — rule should not fire
# ---------------------------------------------------------------------------


def test_no_docstring_returns_empty(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x", "int"),))
    assert check(func, None, _cfg()) == []


def test_no_args_section_returns_empty(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x", "int"),))
    doc = ParsedDocstring(summary="S.", description=None, sections={}, raw="S.")
    assert check(func, doc, _cfg()) == []


def test_no_inline_type_ignored(tmp_path: Path) -> None:
    # x: description — no parenthesized type, nothing to check.
    func = _func(tmp_path / "t.py", params=(_param("x", "float"),))
    doc = _doc([_entry("x", None)])
    assert check(func, doc, _cfg()) == []


def test_types_match_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x", "int"),))
    doc = _doc([_entry("x", "int")])
    assert check(func, doc, _cfg()) == []


def test_unannotated_param_ignored(tmp_path: Path) -> None:
    # Signature has no annotation — cannot compare.
    func = _func(tmp_path / "t.py", params=(_param("x", None),))
    doc = _doc([_entry("x", "int")])
    assert check(func, doc, _cfg()) == []


def test_bound_param_ignored(tmp_path: Path) -> None:
    params = (_param("self", annotation=None, kind="bound"), _param("x", "int"))
    func = _func(tmp_path / "t.py", params=params)
    doc = _doc([_entry("self", "Foo"), _entry("x", "int")])
    assert check(func, doc, _cfg()) == []


def test_param_not_in_entries_ignored(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x", "int"),))
    doc = _doc([_entry("y", "str")])  # y has no annotation in sig
    assert check(func, doc, _cfg()) == []


def test_complex_matching_type_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x", "str | None"),))
    doc = _doc([_entry("x", "str | None")])
    assert check(func, doc, _cfg()) == []


def test_whitespace_normalised_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x", "int"),))
    doc = _doc([_entry("x", "  int  ")])
    assert check(func, doc, _cfg()) == []


# ---------------------------------------------------------------------------
# DOC022 fires
# ---------------------------------------------------------------------------


def test_simple_type_mismatch_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x", "float"),))
    doc = _doc([_entry("x", "int")])
    results = check(func, doc, _cfg())
    assert len(results) == 1
    assert results[0].code == "DOC022"


def test_message_contains_both_types(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x", "float"),))
    doc = _doc([_entry("x", "int")])
    msg = check(func, doc, _cfg())[0].message
    assert "int" in msg
    assert "float" in msg
    assert "x" in msg


def test_severity_is_warning(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x", "float"),))
    doc = _doc([_entry("x", "int")])
    assert check(func, doc, _cfg())[0].severity == Severity.WARNING


def test_no_fix_available(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x", "float"),))
    doc = _doc([_entry("x", "int")])
    result = check(func, doc, _cfg())[0]
    assert result.fix is None
    assert result.unsafe_fix is None


def test_optional_mismatch_fires(tmp_path: Path) -> None:
    # str in signature, str | None in prose — author marked it optional when it isn't.
    func = _func(tmp_path / "t.py", params=(_param("name", "str"),))
    doc = _doc([_entry("name", "str | None")])
    results = check(func, doc, _cfg())
    assert len(results) == 1
    assert results[0].code == "DOC022"


def test_wrong_direction_fires(tmp_path: Path) -> None:
    # str | None in signature but prose says str.
    func = _func(tmp_path / "t.py", params=(_param("name", "str | None"),))
    doc = _doc([_entry("name", "str")])
    results = check(func, doc, _cfg())
    assert len(results) == 1


def test_multiple_params_one_mismatch(tmp_path: Path) -> None:
    params = (_param("a", "int"), _param("b", "float"))
    func = _func(tmp_path / "t.py", params=params)
    doc = _doc([_entry("a", "int"), _entry("b", "int")])  # b drifts
    results = check(func, doc, _cfg())
    assert len(results) == 1
    assert "b" in results[0].message


def test_multiple_params_all_mismatch(tmp_path: Path) -> None:
    params = (_param("a", "int"), _param("b", "str"))
    func = _func(tmp_path / "t.py", params=params)
    doc = _doc([_entry("a", "float"), _entry("b", "bytes")])
    results = check(func, doc, _cfg())
    assert len(results) == 2


def test_entry_without_type_not_counted(tmp_path: Path) -> None:
    # Mix: a has inline type (wrong), b has no inline type.
    params = (_param("a", "float"), _param("b", "str"))
    func = _func(tmp_path / "t.py", params=params)
    doc = _doc([_entry("a", "int"), _entry("b", None)])
    results = check(func, doc, _cfg())
    assert len(results) == 1
    assert "a" in results[0].message


# ---------------------------------------------------------------------------
# Known false positives — notation differences that DO fire (by design)
#
# DOC022 uses plain string comparison. Semantically equivalent types that
# differ in notation (Optional vs |, List vs list, Union vs |) fire as false
# positives. This is documented in the module docstring. These tests pin that
# behaviour so future changes don't accidentally add normalization and hide it.
# ---------------------------------------------------------------------------


def test_false_positive_optional_vs_union(tmp_path: Path) -> None:
    # Optional[str] (prose) ≡ str | None (signature) — same type, fires anyway.
    func = _func(tmp_path / "t.py", params=(_param("x", "str | None"),))
    doc = _doc([_entry("x", "Optional[str]")])
    results = check(func, doc, _cfg())
    assert len(results) == 1  # fires: strings differ, no semantic normalization


def test_false_positive_list_capitalization(tmp_path: Path) -> None:
    # List[int] (pre-PEP 585) vs list[int] (modern) — fires as false positive.
    func = _func(tmp_path / "t.py", params=(_param("x", "list[int]"),))
    doc = _doc([_entry("x", "List[int]")])
    results = check(func, doc, _cfg())
    assert len(results) == 1


def test_false_positive_union_vs_pipe(tmp_path: Path) -> None:
    # Union[str, int] vs str | int — fires as false positive.
    func = _func(tmp_path / "t.py", params=(_param("x", "str | int"),))
    doc = _doc([_entry("x", "Union[str, int]")])
    results = check(func, doc, _cfg())
    assert len(results) == 1


# ---------------------------------------------------------------------------
# End-to-end: parser populates type_annotation from Google-style docstrings
# ---------------------------------------------------------------------------


def test_parser_populates_type_annotation(tmp_path: Path) -> None:
    """Verify griffe propagates inline types through the parser layer."""
    from docpact.parser.docstring import GoogleParser

    raw = """Summary.

    Args:
        x (int): The x value.
        y: No inline type here.
    """
    doc = GoogleParser().parse(raw)
    args = doc.sections.get("Args")
    assert args is not None
    entries = {e.key: e for e in args.entries}
    assert entries["x"].type_annotation == "int"
    assert entries["y"].type_annotation is None


def test_parser_complex_type_annotation(tmp_path: Path) -> None:
    from docpact.parser.docstring import GoogleParser

    raw = """Summary.

    Args:
        name (str | None): Optional name.
    """
    doc = GoogleParser().parse(raw)
    entry = doc.sections["Args"].entries[0]
    assert entry.type_annotation == "str | None"

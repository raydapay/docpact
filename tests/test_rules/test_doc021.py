"""Tests for DOC021 — 'Defaults to X' drift."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from docpact.model.diagnostic import Severity
from docpact.model.function_info import FunctionInfo, ParameterInfo
from docpact.model.parsed_docstring import ParsedDocstring, Section, SectionEntry
from docpact.rules._registry import RuleConfig
from docpact.rules.doc.doc021_default_drift import check


def _param(name: str, default: str | None = None, kind: str = "positional") -> ParameterInfo:
    return ParameterInfo(name=name, annotation=None, default=default, kind=kind)


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
# No-error cases
# ---------------------------------------------------------------------------


def test_no_docstring_returns_empty(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("count", "10"),))
    assert check(func, None, _cfg()) == []


def test_no_args_section_returns_empty(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("count", "10"),))
    doc = ParsedDocstring(summary="S.", description=None, sections={}, raw="S.")
    assert check(func, doc, _cfg()) == []


def test_no_defaults_to_phrase_returns_empty(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("count", "10"),))
    doc = _doc({"count": "Number of items."})
    assert check(func, doc, _cfg()) == []


def test_matching_integer_default_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("count", "10"),))
    doc = _doc({"count": "Number of items. Defaults to 10."})
    assert check(func, doc, _cfg()) == []


def test_matching_string_default_same_quotes_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("name", "'foo'"),))
    doc = _doc({"name": "The name. Defaults to 'foo'."})
    assert check(func, doc, _cfg()) == []


def test_matching_string_default_different_quotes_no_error(tmp_path: Path) -> None:
    # 'foo' in code vs "foo" in docstring — same content after normalization.
    func = _func(tmp_path / "t.py", params=(_param("name", "'foo'"),))
    doc = _doc({"name": 'The name. Defaults to "foo".'})
    assert check(func, doc, _cfg()) == []


def test_matching_bool_default_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("flag", "True"),))
    doc = _doc({"flag": "Enable feature. Defaults to True."})
    assert check(func, doc, _cfg()) == []


def test_matching_none_default_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("x", "None"),))
    doc = _doc({"x": "Optional value. Defaults to None."})
    assert check(func, doc, _cfg()) == []


def test_matching_float_default_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("ratio", "3.14"),))
    doc = _doc({"ratio": "The ratio. Defaults to 3.14."})
    assert check(func, doc, _cfg()) == []


def test_no_default_in_signature_no_error(tmp_path: Path) -> None:
    # No default in signature — cannot compare, so no DOC021.
    func = _func(tmp_path / "t.py", params=(_param("count"),))
    doc = _doc({"count": "Number of items. Defaults to 10."})
    assert check(func, doc, _cfg()) == []


def test_param_not_in_args_entries_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("count", "10"),))
    doc = _doc({"limit": "Number of items. Defaults to 10."})
    assert check(func, doc, _cfg()) == []


def test_bound_param_excluded(tmp_path: Path) -> None:
    params = (_param("self", default=None, kind="bound"), _param("count", "10"))
    func = _func(tmp_path / "t.py", params=params)
    doc = _doc({"count": "Number of items. Defaults to 10."})
    assert check(func, doc, _cfg()) == []


# ---------------------------------------------------------------------------
# Drift detected → DOC021 fires
# ---------------------------------------------------------------------------


def test_integer_drift_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("count", "5"),))
    doc = _doc({"count": "Number of items. Defaults to 10."})
    results = check(func, doc, _cfg())
    assert len(results) == 1
    assert results[0].code == "DOC021"


def test_message_contains_names(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("count", "5"),))
    doc = _doc({"count": "Number of items. Defaults to 10."})
    results = check(func, doc, _cfg())
    assert "count" in results[0].message
    assert "10" in results[0].message
    assert "5" in results[0].message


def test_severity_is_warning(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("count", "5"),))
    doc = _doc({"count": "Number of items. Defaults to 10."})
    results = check(func, doc, _cfg())
    assert results[0].severity == Severity.WARNING


def test_no_fix_available(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("count", "5"),))
    doc = _doc({"count": "Number of items. Defaults to 10."})
    results = check(func, doc, _cfg())
    assert results[0].fix is None
    assert results[0].unsafe_fix is None


def test_bool_drift_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("flag", "False"),))
    doc = _doc({"flag": "Enable feature. Defaults to True."})
    results = check(func, doc, _cfg())
    assert len(results) == 1
    assert results[0].code == "DOC021"


def test_string_drift_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("name", "'bar'"),))
    doc = _doc({"name": "The name. Defaults to 'foo'."})
    results = check(func, doc, _cfg())
    assert len(results) == 1


def test_multiple_params_independent(tmp_path: Path) -> None:
    params = (_param("a", "1"), _param("b", "2"))
    func = _func(tmp_path / "t.py", params=params)
    # a matches, b drifts.
    doc = _doc({"a": "Param a. Defaults to 1.", "b": "Param b. Defaults to 99."})
    results = check(func, doc, _cfg())
    assert len(results) == 1
    assert "b" in results[0].message


def test_case_insensitive_phrase_detection(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("count", "5"),))
    doc = _doc({"count": "Number of items. defaults to 10."})
    results = check(func, doc, _cfg())
    assert len(results) == 1


def test_default_phrase_without_trailing_period(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("count", "5"),))
    doc = _doc({"count": "Number of items. Defaults to 10"})
    results = check(func, doc, _cfg())
    assert len(results) == 1


# ---------------------------------------------------------------------------
# rST double-backtick markup (finding 1)
# ---------------------------------------------------------------------------


def test_rst_backtick_string_default_no_error(tmp_path: Path) -> None:
    # ``"human"`` in docstring should match "human" in signature.
    func = _func(tmp_path / "t.py", params=(_param("tier", '"human"'),))
    doc = _doc({"tier": 'For HTTP keys. Defaults to ``"human"``.'})
    assert check(func, doc, _cfg()) == []


def test_rst_backtick_bool_default_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("flag", "True"),))
    doc = _doc({"flag": "Enable feature. Defaults to ``True``."})
    assert check(func, doc, _cfg()) == []


def test_rst_backtick_drift_fires(tmp_path: Path) -> None:
    # ``"agent"`` in docstring vs "human" in signature → DOC021 fires.
    func = _func(tmp_path / "t.py", params=(_param("tier", '"human"'),))
    doc = _doc({"tier": 'Tier. Defaults to ``"agent"``.'})
    results = check(func, doc, _cfg())
    assert len(results) == 1
    assert results[0].code == "DOC021"


# ---------------------------------------------------------------------------
# Wrapper default extraction (finding 2)
# ---------------------------------------------------------------------------


def test_query_wrapper_false_no_error(tmp_path: Path) -> None:
    # Query(False) effective default is False.
    func = _func(tmp_path / "t.py", params=(_param("verbose", "Query(False)"),))
    doc = _doc({"verbose": "Include details. Defaults to False."})
    assert check(func, doc, _cfg()) == []


def test_field_wrapper_string_no_error(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("name", 'Field("anon")'),))
    doc = _doc({"name": "User name. Defaults to 'anon'."})
    assert check(func, doc, _cfg()) == []


def test_query_wrapper_drift_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py", params=(_param("limit", "Query(10)"),))
    doc = _doc({"limit": "Max results. Defaults to 50."})
    results = check(func, doc, _cfg())
    assert len(results) == 1
    assert results[0].code == "DOC021"


def test_query_false_default_message_shows_wrapper(tmp_path: Path) -> None:
    # The message should show the original signature default, not the extracted one.
    func = _func(tmp_path / "t.py", params=(_param("verbose", "Query(False)"),))
    doc = _doc({"verbose": "Include details. Defaults to true."})
    results = check(func, doc, _cfg())
    assert len(results) == 1
    assert "Query(False)" in results[0].message


# ---------------------------------------------------------------------------
# Literals-only scope (finding 3)
# ---------------------------------------------------------------------------


def test_variable_reference_default_no_error(tmp_path: Path) -> None:
    # SESSION_REGISTRY is not a literal — DOC021 should not fire regardless of prose.
    func = _func(tmp_path / "t.py", params=(_param("registry", "SESSION_REGISTRY"),))
    doc = _doc({"registry": "Active store. Defaults to the session registry."})
    assert check(func, doc, _cfg()) == []


def test_variable_reference_with_contradicting_prose_still_silent(tmp_path: Path) -> None:
    # Known blind spot: we cannot verify constant names. Documented in the rule docstring.
    func = _func(tmp_path / "t.py", params=(_param("timeout", "DEFAULT_TIMEOUT"),))
    doc = _doc({"timeout": "Timeout seconds. Defaults to 99."})
    assert check(func, doc, _cfg()) == []


def test_multi_arg_call_not_extracted(tmp_path: Path) -> None:
    # Query(False, description="...") has multiple args — not extracted, not a literal.
    func = _func(tmp_path / "t.py", params=(_param("flag", 'Query(False, description="x")'),))
    doc = _doc({"flag": "Flag. Defaults to true."})
    assert check(func, doc, _cfg()) == []

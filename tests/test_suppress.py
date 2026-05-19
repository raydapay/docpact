"""Tests for docpact.suppress — parse_suppressions, is_suppressed, apply_suppressions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.suppress import apply_suppressions, is_suppressed, parse_suppressions


def _loc(path: Path, line: int = 1) -> SourceLocation:
    return SourceLocation(file_path=path, line=line, column=0)


def _result(code: str, path: Path, line: int = 1) -> RuleResult:
    return RuleResult(
        code=code,
        severity=Severity.ERROR,
        message="test",
        location=_loc(path, line),
    )


# ---------------------------------------------------------------------------
# parse_suppressions — default marker (nodo)
# ---------------------------------------------------------------------------


def test_no_marker_returns_empty() -> None:
    assert parse_suppressions("def foo(): pass\n") == {}


def test_single_code() -> None:
    result = parse_suppressions("def foo(): pass  # nodo: DOC001\n")
    assert result == {1: frozenset({"DOC001"})}


def test_multiple_codes_comma_separated() -> None:
    result = parse_suppressions("def foo(): pass  # nodo: DOC001, DOC007\n")
    assert result == {1: frozenset({"DOC001", "DOC007"})}


def test_bare_marker_returns_empty_frozenset() -> None:
    result = parse_suppressions("def foo(): pass  # nodo\n")
    assert result == {1: frozenset()}


def test_marker_with_reason_after_dash() -> None:
    source = "def foo(): pass  # nodo: DOC001 -- legacy, tracked in #412\n"
    result = parse_suppressions(source)
    assert result == {1: frozenset({"DOC001"})}


def test_multiple_lines() -> None:
    source = "def foo(): pass  # nodo: DOC001\ndef bar(): pass\ndef baz(): pass  # nodo: DOC007\n"
    result = parse_suppressions(source)
    assert result == {1: frozenset({"DOC001"}), 3: frozenset({"DOC007"})}


def test_marker_spacing_variants() -> None:
    assert parse_suppressions("x  # nodo:DOC001\n") == {1: frozenset({"DOC001"})}
    assert parse_suppressions("x  #nodo: DOC001\n") == {1: frozenset({"DOC001"})}


def test_line_numbers_are_one_based() -> None:
    source = "\n\ndef foo(): pass  # nodo: DOC001\n"
    result = parse_suppressions(source)
    assert 3 in result


# ---------------------------------------------------------------------------
# parse_suppressions — noqa backward-compat via markers=("noqa",)
# ---------------------------------------------------------------------------


def test_noqa_marker_compat() -> None:
    result = parse_suppressions("def foo(): pass  # noqa: DOC001\n", markers=("noqa",))
    assert result == {1: frozenset({"DOC001"})}


def test_noqa_not_matched_by_default_nodo_marker() -> None:
    assert parse_suppressions("def foo(): pass  # noqa: DOC001\n") == {}


def test_nodo_not_matched_by_noqa_marker() -> None:
    assert parse_suppressions("def foo(): pass  # nodo: DOC001\n", markers=("noqa",)) == {}


# ---------------------------------------------------------------------------
# parse_suppressions — multi-marker (nodo + noqa)
# ---------------------------------------------------------------------------


def test_multi_marker_matches_both() -> None:
    markers = ("nodo", "noqa")
    assert parse_suppressions("x  # nodo: DOC001\n", markers=markers) == {1: frozenset({"DOC001"})}
    assert parse_suppressions("x  # noqa: DOC001\n", markers=markers) == {1: frozenset({"DOC001"})}


def test_multi_marker_bare_both() -> None:
    markers = ("nodo", "noqa")
    assert parse_suppressions("x  # nodo\n", markers=markers) == {1: frozenset()}
    assert parse_suppressions("x  # noqa\n", markers=markers) == {1: frozenset()}


# ---------------------------------------------------------------------------
# is_suppressed
# ---------------------------------------------------------------------------


def test_is_suppressed_exact_code_match(tmp_path: Path) -> None:
    f = tmp_path / "t.py"
    r = _result("DOC001", f, line=5)
    suppressions = {5: frozenset({"DOC001"})}
    assert is_suppressed(r, suppressions)


def test_is_suppressed_different_code_not_suppressed(tmp_path: Path) -> None:
    f = tmp_path / "t.py"
    r = _result("DOC007", f, line=5)
    suppressions = {5: frozenset({"DOC001"})}
    assert not is_suppressed(r, suppressions)


def test_is_suppressed_bare_suppresses_all(tmp_path: Path) -> None:
    f = tmp_path / "t.py"
    r = _result("DOC007", f, line=5)
    suppressions = {5: frozenset()}
    assert is_suppressed(r, suppressions)


def test_is_suppressed_no_entry_for_line(tmp_path: Path) -> None:
    f = tmp_path / "t.py"
    r = _result("DOC001", f, line=5)
    suppressions = {3: frozenset({"DOC001"})}
    assert not is_suppressed(r, suppressions)


def test_is_suppressed_multiple_codes(tmp_path: Path) -> None:
    f = tmp_path / "t.py"
    r = _result("DOC007", f, line=2)
    suppressions = {2: frozenset({"DOC001", "DOC007"})}
    assert is_suppressed(r, suppressions)


# ---------------------------------------------------------------------------
# apply_suppressions
# ---------------------------------------------------------------------------


def test_apply_suppressions_removes_suppressed(tmp_path: Path) -> None:
    f = tmp_path / "t.py"
    r1 = _result("DOC001", f, line=1)
    r2 = _result("DOC007", f, line=2)
    suppressions = {f: {1: frozenset({"DOC001"})}}
    visible = apply_suppressions([r1, r2], suppressions)
    assert r1 not in visible
    assert r2 in visible


def test_apply_suppressions_keeps_all_when_no_match(tmp_path: Path) -> None:
    f = tmp_path / "t.py"
    results = [_result("DOC001", f, line=1), _result("DOC007", f, line=2)]
    visible = apply_suppressions(results, {})
    assert visible == results


def test_apply_suppressions_empty_results(tmp_path: Path) -> None:
    assert apply_suppressions([], {}) == []


def test_apply_suppressions_different_files(tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    ra = _result("DOC001", a, line=1)
    rb = _result("DOC001", b, line=1)
    # Suppress DOC001 only in a.py
    suppressions = {a: {1: frozenset({"DOC001"})}}
    visible = apply_suppressions([ra, rb], suppressions)
    assert ra not in visible
    assert rb in visible


# ---------------------------------------------------------------------------
# Integration: suppression in actual source file
# ---------------------------------------------------------------------------


def test_nodo_in_source_suppresses_result(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:  # nodo: DOC001\n    pass\n")
    sups = parse_suppressions(src.read_text())
    r = _result("DOC001", src, line=1)
    assert is_suppressed(r, sups)


def test_noqa_in_source_suppresses_result_when_configured(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:  # noqa: DOC001\n    pass\n")
    sups = parse_suppressions(src.read_text(), markers=("noqa",))
    r = _result("DOC001", src, line=1)
    assert is_suppressed(r, sups)


# ---------------------------------------------------------------------------
# tokenize-based scanner: string literal isolation
# ---------------------------------------------------------------------------


def test_suppression_in_triple_quoted_docstring_not_picked_up() -> None:
    source = (
        "def foo():\n"
        '    """Example:\n'
        "        # nodo: DOC001 -- this is in a docstring\n"
        '    """\n'
        "    pass\n"
    )
    assert parse_suppressions(source) == {}


def test_suppression_in_real_comment_is_picked_up() -> None:
    source = "def foo(): pass  # nodo: DOC007 -- reason\n"
    assert parse_suppressions(source) == {1: frozenset({"DOC007"})}


def test_mixed_file_docstring_ignored_real_comment_captured() -> None:
    source = (
        '"""Module with # nodo: DOC001 -- in module docstring."""\n'
        "\n"
        "def foo(): pass  # nodo: DOC007 -- real\n"
    )
    result = parse_suppressions(source)
    assert result == {3: frozenset({"DOC007"})}
    assert 1 not in result


def test_suppression_in_single_quoted_string_not_picked_up() -> None:
    source = 'x = "# nodo: DOC001 -- in string"\ny = 1\n'
    assert parse_suppressions(source) == {}


def test_suppression_in_fstring_not_picked_up() -> None:
    source = 'x = f"message: {v}  # nodo: DOC001"\ny = 1\n'
    assert parse_suppressions(source) == {}


def test_tokenize_error_returns_empty_dict() -> None:
    source = 'x = 1\ny = """unclosed\n'
    result = parse_suppressions(source)
    assert isinstance(result, dict)


def test_tokenize_error_partial_results_returned() -> None:
    # Line 1 has a valid comment; line 2 opens an unclosed string.
    source = 'x = 1  # nodo: DOC001 -- reason\ny = """unclosed\n'
    result = parse_suppressions(source)
    # COMMENT token for line 1 is emitted before TokenError on line 2.
    assert result == {1: frozenset({"DOC001"})}

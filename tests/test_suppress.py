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
# parse_suppressions
# ---------------------------------------------------------------------------


def test_no_noqa_returns_empty() -> None:
    assert parse_suppressions("def foo(): pass\n") == {}


def test_single_code() -> None:
    result = parse_suppressions("def foo(): pass  # noqa: DOC001\n")
    assert result == {1: frozenset({"DOC001"})}


def test_multiple_codes_comma_separated() -> None:
    result = parse_suppressions("def foo(): pass  # noqa: DOC001, DOC007\n")
    assert result == {1: frozenset({"DOC001", "DOC007"})}


def test_bare_noqa_returns_empty_frozenset() -> None:
    result = parse_suppressions("def foo(): pass  # noqa\n")
    assert result == {1: frozenset()}


def test_noqa_with_reason_after_dash() -> None:
    source = "def foo(): pass  # noqa: DOC001 -- legacy, tracked in #412\n"
    result = parse_suppressions(source)
    assert result == {1: frozenset({"DOC001"})}


def test_multiple_lines() -> None:
    source = "def foo(): pass  # noqa: DOC001\ndef bar(): pass\ndef baz(): pass  # noqa: DOC007\n"
    result = parse_suppressions(source)
    assert result == {1: frozenset({"DOC001"}), 3: frozenset({"DOC007"})}


def test_noqa_spacing_variants() -> None:
    assert parse_suppressions("x  # noqa:DOC001\n") == {1: frozenset({"DOC001"})}
    assert parse_suppressions("x  #noqa: DOC001\n") == {1: frozenset({"DOC001"})}


def test_line_numbers_are_one_based() -> None:
    source = "\n\ndef foo(): pass  # noqa: DOC001\n"
    result = parse_suppressions(source)
    assert 3 in result


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


def test_is_suppressed_bare_noqa_suppresses_all(tmp_path: Path) -> None:
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
# Integration: noqa in actual source file
# ---------------------------------------------------------------------------


def test_noqa_in_source_suppresses_result(tmp_path: Path) -> None:
    from docpact.suppress import parse_suppressions

    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:  # noqa: DOC001\n    pass\n")
    sups = parse_suppressions(src.read_text())
    r = _result("DOC001", src, line=1)
    assert is_suppressed(r, sups)

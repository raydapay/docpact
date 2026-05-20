"""Tests for FIX004 — suppression comment not on a def keyword line."""

from __future__ import annotations

from pathlib import Path

from docpact.model.diagnostic import RuleResult, Severity
from docpact.rules._registry import RuleConfig
from docpact.rules.fix.fix004_misplaced_suppression import check, check_misplaced_suppressions
from docpact.suppress import parse_suppressions


def _cfg() -> RuleConfig:
    return RuleConfig(severity=Severity.WARNING, options={})


def _run(source: str, path: Path) -> list[RuleResult]:
    suppressions = parse_suppressions(source)
    return check_misplaced_suppressions(source, suppressions, path, _cfg())


# ---------------------------------------------------------------------------
# No-error cases
# ---------------------------------------------------------------------------


def test_no_suppressions_returns_empty(tmp_path: Path) -> None:
    source = "def foo(arg: str) -> None:\n    pass\n"
    assert _run(source, tmp_path / "t.py") == []


def test_nodo_on_def_line_no_error(tmp_path: Path) -> None:
    source = "def foo(  # nodo: DOC012 -- reason\n    arg: str,\n) -> None:\n    pass\n"
    assert _run(source, tmp_path / "t.py") == []


def test_nodo_on_async_def_line_no_error(tmp_path: Path) -> None:
    source = "async def foo(  # nodo: DOC012 -- reason\n    arg: str,\n) -> None:\n    pass\n"
    assert _run(source, tmp_path / "t.py") == []


def test_nodo_on_class_line_no_error(tmp_path: Path) -> None:
    source = "class Foo:  # nodo: DOC003 -- reason\n    pass\n"
    assert _run(source, tmp_path / "t.py") == []


def test_nodo_on_line_1_no_error(tmp_path: Path) -> None:
    # Line 1 is valid for module-level DOC002 suppression.
    source = '# nodo: DOC002 -- reason\n"""Module."""\n'
    assert _run(source, tmp_path / "t.py") == []


def test_syntax_error_returns_empty(tmp_path: Path) -> None:
    source = "def foo(:\n    pass\n"
    suppressions = {1: frozenset({"DOC012"})}
    results = check_misplaced_suppressions(source, suppressions, tmp_path / "t.py", _cfg())
    assert results == []


# ---------------------------------------------------------------------------
# FIX004 fires
# ---------------------------------------------------------------------------


def test_nodo_on_closing_paren_line_fires(tmp_path: Path) -> None:
    source = "def foo(\n    arg: str,\n) -> None:  # nodo: DOC012 -- misplaced\n    pass\n"
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1
    assert results[0].code == "FIX004"


def test_closing_paren_hint_present(tmp_path: Path) -> None:
    source = "def foo(\n    arg: str,\n) -> None:  # nodo: DOC012 -- misplaced\n    pass\n"
    results = _run(source, tmp_path / "t.py")
    assert "ruff" in results[0].message


def test_nodo_on_decorator_line_fires(tmp_path: Path) -> None:
    # Decorator is not on line 1 (which has module-level exemption for DOC002).
    source = (
        "x = 1\n@staticmethod  # nodo: DOC012 -- misplaced\ndef foo(arg: str) -> None:\n    pass\n"
    )
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1
    assert results[0].code == "FIX004"


def test_nodo_on_body_line_fires(tmp_path: Path) -> None:
    source = "def foo(arg: str) -> None:\n    x = 1  # nodo: DOC012 -- misplaced\n    pass\n"
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1
    assert results[0].code == "FIX004"


def test_no_ruff_hint_on_non_closing_line(tmp_path: Path) -> None:
    source = "def foo(arg: str) -> None:\n    x = 1  # nodo: DOC012 -- misplaced\n    pass\n"
    results = _run(source, tmp_path / "t.py")
    assert "ruff" not in results[0].message


def test_location_points_to_misplaced_line(tmp_path: Path) -> None:
    source = "def foo(\n    arg: str,\n) -> None:  # nodo: DOC012 -- misplaced\n    pass\n"
    path = tmp_path / "t.py"
    results = _run(source, path)
    assert results[0].location.line == 3
    assert results[0].location.file_path == path


def test_column_points_to_hash(tmp_path: Path) -> None:
    source = "def foo(\n    arg: str,\n) -> None:  # nodo: DOC012 -- misplaced\n    pass\n"
    results = _run(source, tmp_path / "t.py")
    closing_line = ") -> None:  # nodo: DOC012 -- misplaced"
    assert results[0].location.column == closing_line.index("#")


def test_severity_from_config(tmp_path: Path) -> None:
    source = "def foo(\n    arg: str,\n) -> None:  # nodo: DOC012 -- misplaced\n    pass\n"
    suppressions = parse_suppressions(source)
    cfg = RuleConfig(severity=Severity.ERROR, options={})
    results = check_misplaced_suppressions(source, suppressions, tmp_path / "t.py", cfg)
    assert results[0].severity == Severity.ERROR


def test_multiple_misplaced_suppressions(tmp_path: Path) -> None:
    source = (
        "def foo(\n"
        "    arg: str,\n"
        ") -> None:  # nodo: DOC012 -- misplaced\n"
        "    pass\n"
        "@staticmethod  # nodo: DOC007 -- misplaced\n"
        "def bar(x: int) -> None:\n"
        "    pass\n"
    )
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 2
    lines = [r.location.line for r in results]
    assert lines == sorted(lines)


def test_multi_code_suppression_on_closing_paren(tmp_path: Path) -> None:
    # One FIX004 per misplaced line, regardless of how many codes.
    source = "def foo(\n    arg: str,\n) -> None:  # nodo: DOC012, DOC007 -- misplaced\n    pass\n"
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1


def test_closing_paren_without_arrow_no_ruff_hint(tmp_path: Path) -> None:
    # A bare `)` without `->` should fire FIX004 but not the ruff hint.
    source = "def foo(\n    arg: str,\n):  # nodo: DOC012 -- misplaced\n    pass\n"
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1
    assert "ruff" not in results[0].message


# ---------------------------------------------------------------------------
# Fixture-based integration test
# ---------------------------------------------------------------------------


def test_fixture_correct_placements_only(tmp_path: Path) -> None:
    fixture = Path(__file__).parent.parent / "fixtures" / "fix004_misplaced.py"
    source = fixture.read_text(encoding="utf-8")
    suppressions = parse_suppressions(source)
    results = check_misplaced_suppressions(source, suppressions, fixture, _cfg())
    # Correct placements (def/class lines) must not appear in results.
    # Misplaced ones (closing paren, decorator, body) must appear.
    assert len(results) == 3  # closing paren, decorator, body line


# ---------------------------------------------------------------------------
# Stub check() function
# ---------------------------------------------------------------------------


def test_stub_check_returns_empty(tmp_path: Path) -> None:
    from docpact.model.function_info import FunctionInfo

    func = FunctionInfo(
        name="foo",
        file_path=tmp_path / "t.py",
        line=1,
        column=0,
        parameters=(),
        return_annotation=None,
        decorators=(),
        docstring_raw=None,
        docstring_line=1,
        containing_class=None,
        def_start_offset=0,
        def_end_offset=10,
        docstring_start_offset=None,
        docstring_end_offset=None,
    )
    assert check(func, None, _cfg()) == []

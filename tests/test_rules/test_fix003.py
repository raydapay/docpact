"""Tests for FIX003 — stale suppression comment."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig
from docpact.rules.fix.fix003_stale_suppression import check, check_stale_suppressions


def _cfg() -> RuleConfig:
    return RuleConfig(severity=Severity.WARNING, options={})


def _violation(file_path: Path, line: int, code: str) -> RuleResult:
    return RuleResult(
        code=code,
        severity=Severity.WARNING,
        message="test violation",
        location=SourceLocation(file_path=file_path, line=line, column=0),
    )


def _run(
    source: str,
    path: Path,
    suppressions: dict[int, frozenset[str]],
    violations: list[RuleResult],
) -> list[RuleResult]:
    return check_stale_suppressions(source, suppressions, violations, path, _cfg())


# ---------------------------------------------------------------------------
# No-error cases
# ---------------------------------------------------------------------------


def test_no_suppressions_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "t.py"
    assert _run("x = 1\n", path, {}, []) == []


def test_suppression_with_active_violation_no_error(tmp_path: Path) -> None:
    path = tmp_path / "t.py"
    source = "def foo():  # nodo: DOC007 -- reason\n    pass\n"
    suppressions = {1: frozenset({"DOC007"})}
    violations = [_violation(path, 1, "DOC007")]
    assert _run(source, path, suppressions, violations) == []


def test_bare_suppression_ignored(tmp_path: Path) -> None:
    # Bare suppressions (empty code set) are FIX001's domain; FIX003 skips them.
    path = tmp_path / "t.py"
    source = "def foo():  # nodo\n    pass\n"
    suppressions = {1: frozenset()}
    assert _run(source, path, suppressions, []) == []


def test_multi_code_suppression_one_active_one_stale(tmp_path: Path) -> None:
    # DOC007 active, DOC012 stale → only DOC012 fires.
    path = tmp_path / "t.py"
    source = "def foo():  # nodo: DOC007, DOC012 -- reason\n    pass\n"
    suppressions = {1: frozenset({"DOC007", "DOC012"})}
    violations = [_violation(path, 1, "DOC007")]
    results = _run(source, path, suppressions, violations)
    assert len(results) == 1
    assert "DOC012" in results[0].message


# ---------------------------------------------------------------------------
# FIX003 fires
# ---------------------------------------------------------------------------


def test_stale_suppression_fires(tmp_path: Path) -> None:
    path = tmp_path / "t.py"
    source = "def foo():  # nodo: DOC007 -- baseline\n    pass\n"
    suppressions = {1: frozenset({"DOC007"})}
    results = _run(source, path, suppressions, violations=[])
    assert len(results) == 1
    assert results[0].code == "FIX003"


def test_message_contains_suppressed_code(tmp_path: Path) -> None:
    path = tmp_path / "t.py"
    source = "def foo():  # nodo: DOC007 -- baseline\n    pass\n"
    suppressions = {1: frozenset({"DOC007"})}
    results = _run(source, path, suppressions, violations=[])
    assert "DOC007" in results[0].message


def test_location_points_to_suppression_line(tmp_path: Path) -> None:
    path = tmp_path / "t.py"
    source = "x = 1\ndef foo():  # nodo: DOC007 -- baseline\n    pass\n"
    suppressions = {2: frozenset({"DOC007"})}
    results = _run(source, path, suppressions, violations=[])
    assert results[0].location.line == 2
    assert results[0].location.file_path == path


def test_column_points_to_hash(tmp_path: Path) -> None:
    path = tmp_path / "t.py"
    source = "def foo():  # nodo: DOC007 -- baseline\n    pass\n"
    suppressions = {1: frozenset({"DOC007"})}
    results = _run(source, path, suppressions, violations=[])
    assert results[0].location.column == source.index("#")


def test_severity_from_config(tmp_path: Path) -> None:
    path = tmp_path / "t.py"
    source = "def foo():  # nodo: DOC007 -- baseline\n    pass\n"
    suppressions = {1: frozenset({"DOC007"})}
    cfg = RuleConfig(severity=Severity.ERROR, options={})
    results = check_stale_suppressions(source, suppressions, [], path, cfg)
    assert results[0].severity == Severity.ERROR


def test_multiple_stale_suppressions_on_different_lines(tmp_path: Path) -> None:
    path = tmp_path / "t.py"
    source = (
        "def foo():  # nodo: DOC007 -- baseline\n"
        "    pass\n"
        "def bar():  # nodo: DOC012 -- baseline\n"
        "    pass\n"
    )
    suppressions = {1: frozenset({"DOC007"}), 3: frozenset({"DOC012"})}
    results = _run(source, path, suppressions, violations=[])
    assert len(results) == 2
    lines = [r.location.line for r in results]
    assert lines == sorted(lines)


def test_multi_code_all_stale_emits_per_code(tmp_path: Path) -> None:
    path = tmp_path / "t.py"
    source = "def foo():  # nodo: DOC007, DOC012 -- baseline\n    pass\n"
    suppressions = {1: frozenset({"DOC007", "DOC012"})}
    results = _run(source, path, suppressions, violations=[])
    assert len(results) == 2
    codes = {r.message for r in results}
    assert any("DOC007" in m for m in codes)
    assert any("DOC012" in m for m in codes)


def test_violation_on_different_line_still_stale(tmp_path: Path) -> None:
    # A violation for DOC007 on line 5 does not satisfy a suppression on line 1.
    path = tmp_path / "t.py"
    source = "def foo():  # nodo: DOC007 -- baseline\n    pass\n"
    suppressions = {1: frozenset({"DOC007"})}
    violations = [_violation(path, 5, "DOC007")]
    results = _run(source, path, suppressions, violations)
    assert len(results) == 1


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

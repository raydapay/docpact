"""Tests for docpact.fix — apply_fixes, diff_fixes, conflict detection."""

from __future__ import annotations

from pathlib import Path

from docpact.fix import ConflictError, apply_fixes, diff_fixes
from docpact.model.diagnostic import Fix, RuleResult, Severity, SourceLocation


def _loc(path: Path) -> SourceLocation:
    return SourceLocation(file_path=path, line=1, column=0)


def _fix(path: Path, start: int, end: int, replacement: str, desc: str = "fix") -> Fix:
    return Fix(
        description=desc,
        file_path=path,
        start_offset=start,
        end_offset=end,
        replacement=replacement,
    )


def _result(path: Path, fix: Fix | None = None, unsafe_fix: Fix | None = None) -> RuleResult:
    return RuleResult(
        code="DOC001",
        severity=Severity.ERROR,
        message="missing docstring",
        location=_loc(path),
        fix=fix,
        unsafe_fix=unsafe_fix,
    )


# ---------------------------------------------------------------------------
# apply_fixes — basic application
# ---------------------------------------------------------------------------


def test_apply_fixes_inserts_text(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_bytes(b"def foo():\n    pass\n")
    offset = len(b"def foo():\n")
    fix = _fix(src, offset, offset, '    """Do something."""\n')
    results = [_result(src, fix=fix)]
    modified, conflicts = apply_fixes(results)
    assert src in modified
    assert conflicts == []
    content = src.read_text()
    assert '"""Do something."""' in content


def test_apply_fixes_replaces_text(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_bytes(b"hello world")
    fix = _fix(src, 6, 11, "Python")
    results = [_result(src, fix=fix)]
    apply_fixes(results)
    assert src.read_bytes() == b"hello Python"


def test_apply_fixes_deletes_text(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_bytes(b"aXb")
    fix = _fix(src, 1, 2, "")
    results = [_result(src, fix=fix)]
    apply_fixes(results)
    assert src.read_bytes() == b"ab"


def test_apply_fixes_returns_modified_path(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_bytes(b"x")
    fix = _fix(src, 0, 1, "y")
    modified, _ = apply_fixes([_result(src, fix=fix)])
    assert src in modified


def test_apply_fixes_no_write_when_unchanged(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_bytes(b"x")
    # replacement identical to existing content
    fix = _fix(src, 0, 1, "x")
    modified, _ = apply_fixes([_result(src, fix=fix)])
    assert src not in modified


def test_apply_fixes_no_fix_is_noop(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_bytes(b"unchanged")
    results = [_result(src, fix=None)]
    modified, conflicts = apply_fixes(results)
    assert modified == []
    assert conflicts == []
    assert src.read_bytes() == b"unchanged"


# ---------------------------------------------------------------------------
# Multiple fixes in one file (end-to-start ordering)
# ---------------------------------------------------------------------------


def test_apply_multiple_fixes_same_file(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_bytes(b"abcde")
    # Replace 'a' (0,1) with 'X' and 'd' (3,4) with 'Y' — non-overlapping.
    fix_a = _fix(src, 0, 1, "X")
    fix_d = _fix(src, 3, 4, "Y")
    results = [_result(src, fix=fix_a), _result(src, fix=fix_d)]
    apply_fixes(results)
    assert src.read_bytes() == b"XbcYe"


def test_apply_fixes_multiple_files(tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_bytes(b"aaa")
    b.write_bytes(b"bbb")
    fix_a = _fix(a, 0, 3, "AAA")
    fix_b = _fix(b, 0, 3, "BBB")
    modified, _ = apply_fixes([_result(a, fix=fix_a), _result(b, fix=fix_b)])
    assert set(modified) == {a, b}
    assert a.read_bytes() == b"AAA"
    assert b.read_bytes() == b"BBB"


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_duplicate_fixes_applied_once(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_bytes(b"x")
    fix = _fix(src, 0, 1, "y")
    # Two results with identical fix payloads.
    results = [_result(src, fix=fix), _result(src, fix=fix)]
    apply_fixes(results)
    assert src.read_bytes() == b"y"


# ---------------------------------------------------------------------------
# Unsafe fixes
# ---------------------------------------------------------------------------


def test_unsafe_fix_not_applied_without_flag(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_bytes(b"original")
    unsafe = _fix(src, 0, 8, "replaced")
    results = [_result(src, unsafe_fix=unsafe)]
    modified, _ = apply_fixes(results, unsafe=False)
    assert src not in modified
    assert src.read_bytes() == b"original"


def test_unsafe_fix_applied_with_flag(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_bytes(b"original")
    unsafe = _fix(src, 0, 8, "replaced")
    results = [_result(src, unsafe_fix=unsafe)]
    modified, _ = apply_fixes(results, unsafe=True)
    assert src in modified
    assert src.read_bytes() == b"replaced"


def test_safe_and_unsafe_fix_both_applied(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_bytes(b"abcd")
    safe = _fix(src, 0, 2, "XX")
    unsafe = _fix(src, 2, 4, "YY")
    results = [_result(src, fix=safe, unsafe_fix=unsafe)]
    apply_fixes(results, unsafe=True)
    assert src.read_bytes() == b"XXYY"


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


def test_overlapping_fixes_yield_conflict(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_bytes(b"abcde")
    fix_a = _fix(src, 0, 3, "X")  # [0, 3)
    fix_b = _fix(src, 2, 5, "Y")  # [2, 5) — overlaps with fix_a
    modified, conflicts = apply_fixes([_result(src, fix=fix_a), _result(src, fix=fix_b)])
    assert src not in modified
    assert len(conflicts) == 1
    assert isinstance(conflicts[0], ConflictError)
    # File is unchanged when conflicts exist.
    assert src.read_bytes() == b"abcde"


def test_adjacent_fixes_do_not_conflict(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_bytes(b"abcd")
    fix_a = _fix(src, 0, 2, "XX")  # [0, 2)
    fix_b = _fix(src, 2, 4, "YY")  # [2, 4) — adjacent, not overlapping
    _, conflicts = apply_fixes([_result(src, fix=fix_a), _result(src, fix=fix_b)])
    assert conflicts == []
    assert src.read_bytes() == b"XXYY"


def test_conflict_error_str_contains_offsets(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_bytes(b"abcde")
    fix_a = _fix(src, 0, 3, "X")
    fix_b = _fix(src, 1, 4, "Y")
    _, conflicts = apply_fixes([_result(src, fix=fix_a), _result(src, fix=fix_b)])
    msg = str(conflicts[0])
    assert "0" in msg and "3" in msg


def test_conflict_in_one_file_does_not_affect_other(tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_bytes(b"xxx")
    b.write_bytes(b"yyy")
    # Conflict in a.py
    fix_a1 = _fix(a, 0, 2, "A")
    fix_a2 = _fix(a, 1, 3, "B")
    # Clean fix in b.py
    fix_b = _fix(b, 0, 3, "ZZZ")
    results = [
        _result(a, fix=fix_a1),
        _result(a, fix=fix_a2),
        _result(b, fix=fix_b),
    ]
    modified, conflicts = apply_fixes(results)
    assert b in modified
    assert a not in modified
    assert len(conflicts) == 1
    assert b.read_bytes() == b"ZZZ"


# ---------------------------------------------------------------------------
# diff_fixes
# ---------------------------------------------------------------------------


def test_diff_fixes_returns_unified_diff(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_bytes(b"x = 1\n")
    fix = _fix(src, 0, 6, "x = 2\n")
    patch = diff_fixes([_result(src, fix=fix)])
    assert "---" in patch
    assert "+++" in patch
    assert "-x = 1" in patch
    assert "+x = 2" in patch


def test_diff_fixes_empty_when_no_changes(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_bytes(b"x = 1\n")
    fix = _fix(src, 0, 6, "x = 1\n")  # same content
    patch = diff_fixes([_result(src, fix=fix)])
    assert patch == ""


def test_diff_fixes_does_not_write_file(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    original = b"original content\n"
    src.write_bytes(original)
    fix = _fix(src, 0, len(original), "changed\n")
    diff_fixes([_result(src, fix=fix)])
    assert src.read_bytes() == original


def test_diff_fixes_skips_conflicting_files(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_bytes(b"abcde")
    fix_a = _fix(src, 0, 3, "X")
    fix_b = _fix(src, 1, 4, "Y")
    patch = diff_fixes([_result(src, fix=fix_a), _result(src, fix=fix_b)])
    assert patch == ""


def test_diff_fixes_respects_unsafe_flag(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_bytes(b"original\n")
    unsafe = _fix(src, 0, 9, "changed\n")
    patch_without = diff_fixes([_result(src, unsafe_fix=unsafe)], unsafe=False)
    patch_with = diff_fixes([_result(src, unsafe_fix=unsafe)], unsafe=True)
    assert patch_without == ""
    assert "changed" in patch_with


# ---------------------------------------------------------------------------
# CLI integration for --fix and --diff
# ---------------------------------------------------------------------------


def test_cli_fix_applies_doc001_stub(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from docpact.cli import main

    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")

    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(main, ["check", "--fix", str(src)], catch_exceptions=False)

    assert result.exit_code == 0
    content = src.read_text()
    assert '"""' in content  # stub was inserted


def test_cli_diff_shows_patch_without_writing(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from docpact.cli import main

    src = tmp_path / "t.py"
    original = "def foo(x: int) -> None:\n    pass\n"
    src.write_text(original)

    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(main, ["check", "--diff", str(src)], catch_exceptions=False)

    assert "+++" in result.output
    assert src.read_text() == original  # file unchanged

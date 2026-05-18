"""Tests for DOC003 — missing docstring on a class definition."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from docpact.model.diagnostic import Severity
from docpact.rules._registry import RuleConfig
from docpact.rules.doc.doc003_class_docstring import check, check_class_docstrings


def _cfg(severity: Severity = Severity.WARNING) -> RuleConfig:
    return RuleConfig(severity=severity, options={})


def _run(source: str, path: Path) -> list:
    return check_class_docstrings(source, path, _cfg())


# ---------------------------------------------------------------------------
# No error cases
# ---------------------------------------------------------------------------


def test_class_with_docstring_no_error(tmp_path: Path) -> None:
    source = 'class Foo:\n    """Foo class."""\n    pass\n'
    assert _run(source, tmp_path / "t.py") == []


def test_class_with_multiline_docstring_no_error(tmp_path: Path) -> None:
    source = 'class Foo:\n    """First line.\n\n    Detail.\n    """\n    pass\n'
    assert _run(source, tmp_path / "t.py") == []


def test_no_classes_no_error(tmp_path: Path) -> None:
    source = "def foo(): pass\n"
    assert _run(source, tmp_path / "t.py") == []


def test_syntax_error_no_error(tmp_path: Path) -> None:
    assert _run("class (:\n", tmp_path / "t.py") == []


def test_nested_class_with_docstring_no_error(tmp_path: Path) -> None:
    source = (
        'class Outer:\n    """Outer."""\n    class Inner:\n        """Inner."""\n        pass\n'
    )
    assert _run(source, tmp_path / "t.py") == []


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_class_without_docstring_fires(tmp_path: Path) -> None:
    source = "class Foo:\n    pass\n"
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1
    assert results[0].code == "DOC003"


def test_message_contains_class_name(tmp_path: Path) -> None:
    source = "class MyClass:\n    pass\n"
    results = _run(source, tmp_path / "t.py")
    assert "MyClass" in results[0].message


def test_class_with_only_pass_fires(tmp_path: Path) -> None:
    source = "class Empty:\n    ...\n"
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1


def test_class_starting_with_assignment_fires(tmp_path: Path) -> None:
    source = "class Foo:\n    x = 1\n"
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1


def test_multiple_classes_each_emit(tmp_path: Path) -> None:
    source = "class Foo:\n    pass\nclass Bar:\n    pass\n"
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 2
    codes = {r.code for r in results}
    assert codes == {"DOC003"}


def test_nested_class_without_docstring_fires(tmp_path: Path) -> None:
    source = 'class Outer:\n    """Outer."""\n    class Inner:\n        pass\n'
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1
    assert "Inner" in results[0].message


def test_location_points_to_class_line(tmp_path: Path) -> None:
    source = "x = 1\nclass Foo:\n    pass\n"
    results = _run(source, tmp_path / "t.py")
    assert results[0].location.line == 2
    assert results[0].location.column == 0


def test_indented_class_column_correct(tmp_path: Path) -> None:
    source = 'class Outer:\n    """Outer."""\n    class Inner:\n        pass\n'
    results = _run(source, tmp_path / "t.py")
    assert results[0].location.column == 4


def test_file_path_in_location(tmp_path: Path) -> None:
    path = tmp_path / "t.py"
    results = _run("class Foo:\n    pass\n", path)
    assert results[0].location.file_path == path


def test_severity_from_config(tmp_path: Path) -> None:
    cfg = RuleConfig(severity=Severity.ERROR, options={})
    results = check_class_docstrings("class Foo:\n    pass\n", tmp_path / "t.py", cfg)
    assert results[0].severity == Severity.ERROR


def test_default_severity_is_warning(tmp_path: Path) -> None:
    results = _run("class Foo:\n    pass\n", tmp_path / "t.py")
    assert results[0].severity == Severity.WARNING


def test_results_in_source_order(tmp_path: Path) -> None:
    source = "class A:\n    pass\nclass B:\n    pass\nclass C:\n    pass\n"
    results = _run(source, tmp_path / "t.py")
    lines = [r.location.line for r in results]
    assert lines == sorted(lines)


# ---------------------------------------------------------------------------
# Stub check() function
# ---------------------------------------------------------------------------


def test_stub_check_function_returns_empty(tmp_path: Path) -> None:
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

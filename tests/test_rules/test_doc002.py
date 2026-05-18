"""Tests for DOC002 — missing module-level docstring."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from docpact.model.diagnostic import Severity
from docpact.rules._registry import RuleConfig
from docpact.rules.doc.doc002_module_docstring import check, check_module_docstring


def _cfg(severity: Severity = Severity.WARNING) -> RuleConfig:
    return RuleConfig(severity=severity, options={})


def _run(source: str, path: Path) -> list:
    return check_module_docstring(source, path, _cfg())


# ---------------------------------------------------------------------------
# No error cases
# ---------------------------------------------------------------------------


def test_module_with_docstring_no_error(tmp_path: Path) -> None:
    source = '"""Module docstring."""\n\nimport os\n'
    assert _run(source, tmp_path / "m.py") == []


def test_module_with_multiline_docstring_no_error(tmp_path: Path) -> None:
    source = '"""First line.\n\nMore detail.\n"""\nimport os\n'
    assert _run(source, tmp_path / "m.py") == []


def test_empty_file_no_error(tmp_path: Path) -> None:
    # Empty files are silently skipped — no docstring required for nothing.
    assert _run("", tmp_path / "m.py") == []


def test_syntax_error_no_error(tmp_path: Path) -> None:
    # Files that fail to parse don't produce DOC002 — a SyntaxError is a
    # different problem, not a missing docstring.
    assert _run("def (:\n", tmp_path / "m.py") == []


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_module_with_no_docstring_fires(tmp_path: Path) -> None:
    source = "import os\n"
    results = _run(source, tmp_path / "m.py")
    assert len(results) == 1
    assert results[0].code == "DOC002"


def test_module_starting_with_assignment_fires(tmp_path: Path) -> None:
    source = "X = 1\n"
    results = _run(source, tmp_path / "m.py")
    assert len(results) == 1
    assert results[0].code == "DOC002"


def test_module_starting_with_class_fires(tmp_path: Path) -> None:
    source = "class Foo: pass\n"
    results = _run(source, tmp_path / "m.py")
    assert len(results) == 1
    assert results[0].code == "DOC002"


def test_module_starting_with_comment_fires(tmp_path: Path) -> None:
    # A # comment is not a docstring.
    source = "# not a docstring\nimport os\n"
    results = _run(source, tmp_path / "m.py")
    assert len(results) == 1
    assert results[0].code == "DOC002"


def test_location_is_line_1_col_0(tmp_path: Path) -> None:
    path = tmp_path / "m.py"
    results = _run("import os\n", path)
    assert results[0].location.line == 1
    assert results[0].location.column == 0


def test_file_path_in_location(tmp_path: Path) -> None:
    path = tmp_path / "m.py"
    results = _run("import os\n", path)
    assert results[0].location.file_path == path


def test_severity_from_config(tmp_path: Path) -> None:
    source = "import os\n"
    cfg = RuleConfig(severity=Severity.ERROR, options={})
    results = check_module_docstring(source, tmp_path / "m.py", cfg)
    assert results[0].severity == Severity.ERROR


def test_default_severity_is_warning(tmp_path: Path) -> None:
    results = _run("import os\n", tmp_path / "m.py")
    assert results[0].severity == Severity.WARNING


# ---------------------------------------------------------------------------
# Stub check() function
# ---------------------------------------------------------------------------


def test_stub_check_function_returns_empty(tmp_path: Path) -> None:
    from docpact.model.function_info import FunctionInfo

    func = FunctionInfo(
        name="foo",
        file_path=tmp_path / "m.py",
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

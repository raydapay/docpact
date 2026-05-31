"""Tests for DOC050 — Pydantic model field missing Field(description=...)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from docpact.model.diagnostic import Severity
from docpact.parser.pydantic_model import (
    is_classvar as _is_classvar,
)
from docpact.parser.pydantic_model import (
    is_pydantic_model as _is_pydantic_model,
)
from docpact.rules._registry import RuleConfig
from docpact.rules.doc.doc050_pydantic_field import (
    _has_field_description,
    check,
    check_pydantic_fields,
)


def _cfg(severity: Severity = Severity.WARNING) -> RuleConfig:
    return RuleConfig(severity=severity, options={})


def _run(source: str, path: Path) -> list:
    return check_pydantic_fields(source, path, _cfg())


# ---------------------------------------------------------------------------
# No error cases
# ---------------------------------------------------------------------------


def test_field_with_description_no_error(tmp_path: Path) -> None:
    source = (
        "from pydantic import BaseModel, Field\n"
        "class User(BaseModel):\n"
        '    name: str = Field(description="Full name of the user.")\n'
    )
    assert _run(source, tmp_path / "t.py") == []


def test_field_with_qualified_pydantic_field_no_error(tmp_path: Path) -> None:
    source = (
        "import pydantic\n"
        "class User(pydantic.BaseModel):\n"
        '    name: str = pydantic.Field(description="Full name.")\n'
    )
    assert _run(source, tmp_path / "t.py") == []


def test_non_pydantic_class_skipped(tmp_path: Path) -> None:
    source = "class Foo:\n    name: str\n"
    assert _run(source, tmp_path / "t.py") == []


def test_private_field_skipped(tmp_path: Path) -> None:
    source = "from pydantic import BaseModel\nclass User(BaseModel):\n    _secret: str\n"
    assert _run(source, tmp_path / "t.py") == []


def test_classvar_field_skipped(tmp_path: Path) -> None:
    source = (
        "from typing import ClassVar\n"
        "from pydantic import BaseModel\n"
        "class User(BaseModel):\n"
        "    registry: ClassVar[dict] = {}\n"
    )
    assert _run(source, tmp_path / "t.py") == []


def test_syntax_error_no_error(tmp_path: Path) -> None:
    assert _run("class (:\n", tmp_path / "t.py") == []


def test_empty_file_no_error(tmp_path: Path) -> None:
    assert _run("", tmp_path / "t.py") == []


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_bare_annotation_fires(tmp_path: Path) -> None:
    source = "from pydantic import BaseModel\nclass User(BaseModel):\n    name: str\n"
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1
    assert results[0].code == "DOC050"
    assert "name" in results[0].message


def test_field_without_description_fires(tmp_path: Path) -> None:
    source = (
        "from pydantic import BaseModel, Field\n"
        "class User(BaseModel):\n"
        "    name: str = Field(default='anon')\n"
    )
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1
    assert "name" in results[0].message


def test_field_with_empty_description_fires(tmp_path: Path) -> None:
    source = (
        "from pydantic import BaseModel, Field\n"
        "class User(BaseModel):\n"
        '    name: str = Field(description="")\n'
    )
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1


def test_non_field_default_fires(tmp_path: Path) -> None:
    source = 'from pydantic import BaseModel\nclass User(BaseModel):\n    name: str = "default"\n'
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1


def test_multiple_fields_each_emit(tmp_path: Path) -> None:
    source = "from pydantic import BaseModel\nclass User(BaseModel):\n    name: str\n    age: int\n"
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 2
    names = {r.message for r in results}
    assert any("name" in m for m in names)
    assert any("age" in m for m in names)


def test_mixed_fields_only_undocumented_emit(tmp_path: Path) -> None:
    source = (
        "from pydantic import BaseModel, Field\n"
        "class User(BaseModel):\n"
        '    name: str = Field(description="Full name.")\n'
        "    age: int\n"
    )
    results = _run(source, tmp_path / "t.py")
    assert len(results) == 1
    assert "age" in results[0].message


def test_location_points_to_field_line(tmp_path: Path) -> None:
    source = "from pydantic import BaseModel\nclass User(BaseModel):\n    name: str\n"
    results = _run(source, tmp_path / "t.py")
    assert results[0].location.line == 3
    assert results[0].location.column == 4


def test_file_path_in_location(tmp_path: Path) -> None:
    path = tmp_path / "t.py"
    source = "from pydantic import BaseModel\nclass U(BaseModel):\n    x: int\n"
    results = _run(source, path)
    assert results[0].location.file_path == path


def test_custom_basemodel_subclass(tmp_path: Path) -> None:
    # Inheriting from a custom class that itself inherits from BaseModel.
    source = (
        "from pydantic import BaseModel\n"
        "class MyBaseModel(BaseModel): pass\n"
        "class User(MyBaseModel):\n"
        "    name: str\n"
    )
    # MyBaseModel contains "BaseModel" in its name → treated as Pydantic model.
    results = _run(source, tmp_path / "t.py")
    assert any("name" in r.message for r in results)


def test_severity_from_config(tmp_path: Path) -> None:
    source = "from pydantic import BaseModel\nclass U(BaseModel):\n    x: int\n"
    cfg = RuleConfig(severity=Severity.ERROR, options={})
    results = check_pydantic_fields(source, tmp_path / "t.py", cfg)
    assert results[0].severity == Severity.ERROR


def test_default_severity_is_warning(tmp_path: Path) -> None:
    source = "from pydantic import BaseModel\nclass U(BaseModel):\n    x: int\n"
    results = _run(source, tmp_path / "t.py")
    assert results[0].severity == Severity.WARNING


def test_results_in_source_order(tmp_path: Path) -> None:
    source = (
        "from pydantic import BaseModel\n"
        "class U(BaseModel):\n"
        "    a: int\n"
        "    b: str\n"
        "    c: float\n"
    )
    results = _run(source, tmp_path / "t.py")
    lines = [r.location.line for r in results]
    assert lines == sorted(lines)


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------


def test_is_pydantic_model_basemodel() -> None:
    import ast as _ast

    node = _ast.parse("class Foo(BaseModel): pass").body[0]
    assert isinstance(node, _ast.ClassDef)
    assert _is_pydantic_model(node)


def test_is_pydantic_model_qualified() -> None:
    import ast as _ast

    node = _ast.parse("class Foo(pydantic.BaseModel): pass").body[0]
    assert isinstance(node, _ast.ClassDef)
    assert _is_pydantic_model(node)


def test_is_not_pydantic_model() -> None:
    import ast as _ast

    node = _ast.parse("class Foo(SomeOtherClass): pass").body[0]
    assert isinstance(node, _ast.ClassDef)
    assert not _is_pydantic_model(node)


def test_is_classvar_positive() -> None:
    import ast as _ast

    ann = _ast.parse("ClassVar[int]", mode="eval").body
    assert _is_classvar(ann)


def test_is_classvar_negative() -> None:
    import ast as _ast

    ann = _ast.parse("int", mode="eval").body
    assert not _is_classvar(ann)


def test_has_field_description_positive() -> None:
    import ast as _ast

    call = _ast.parse('Field(description="desc")', mode="eval").body
    assert _has_field_description(call)


def test_has_field_description_negative_no_desc() -> None:
    import ast as _ast

    call = _ast.parse("Field(default=1)", mode="eval").body
    assert not _has_field_description(call)


def test_has_field_description_negative_not_field() -> None:
    import ast as _ast

    call = _ast.parse('Other(description="desc")', mode="eval").body
    assert not _has_field_description(call)


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

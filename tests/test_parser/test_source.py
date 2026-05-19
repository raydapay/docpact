"""Tests for docpact.parser.source — extract_functions."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from docpact.parser.source import extract_functions, parse_all_names, parse_tier_pragma

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fn(functions: list[FunctionInfo], name: str) -> FunctionInfo:
    """Look up a function by name from the extracted list."""
    for f in functions:
        if f.name == name:
            return f
    raise KeyError(f"No function named {name!r} in {[f.name for f in functions]}")


def _params_of(fn: FunctionInfo) -> list[tuple[str, str]]:
    """Return (name, kind) for each parameter."""
    return [(p.name, p.kind) for p in fn.parameters]


# ---------------------------------------------------------------------------
# Basic extraction
# ---------------------------------------------------------------------------


def test_extract_returns_list(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo(): pass\n")
    result = extract_functions(src)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].name == "foo"


def test_source_order_preserved(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def alpha(): pass\ndef beta(): pass\ndef gamma(): pass\n")
    names = [f.name for f in extract_functions(src)]
    assert names == ["alpha", "beta", "gamma"]


def test_file_path_set(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo(): pass\n")
    fn = extract_functions(src)[0]
    assert fn.file_path == src


def test_line_column_set(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo(): pass\n")
    fn = extract_functions(src)[0]
    assert fn.line == 1
    assert fn.column == 0


def test_indented_method_column(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("class C:\n    def method(self): pass\n")
    fn = _fn(extract_functions(src), "method")
    assert fn.column == 4


def test_async_function_included(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("async def afn(): pass\n")
    fns = extract_functions(src)
    assert len(fns) == 1
    assert fns[0].name == "afn"


def test_syntax_error_raises(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def (: pass\n")
    with pytest.raises(SyntaxError):
        extract_functions(src)


def test_oserror_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        extract_functions(tmp_path / "nonexistent.py")


# ---------------------------------------------------------------------------
# Docstring extraction
# ---------------------------------------------------------------------------


def test_docstring_raw_present(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text('def foo():\n    """My docstring."""\n    pass\n')
    fn = extract_functions(src)[0]
    assert fn.docstring_raw == "My docstring."


def test_docstring_raw_absent(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo():\n    pass\n")
    fn = extract_functions(src)[0]
    assert fn.docstring_raw is None


def test_docstring_multiline(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text('def foo():\n    """First line.\n\n    Second para.\n    """\n    pass\n')
    fn = extract_functions(src)[0]
    assert fn.docstring_raw is not None
    assert "First line." in fn.docstring_raw


def test_docstring_line_set(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text('def foo():\n    """Doc."""\n    pass\n')
    fn = extract_functions(src)[0]
    assert fn.docstring_line == 2


# ---------------------------------------------------------------------------
# Byte offsets
# ---------------------------------------------------------------------------


def test_def_start_offset_zero(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo(): pass\n")
    fn = extract_functions(src)[0]
    # "def" starts at byte 0
    assert fn.def_start_offset == 0


def test_def_start_offset_indented(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("class C:\n    def method(self): pass\n")
    fn = _fn(extract_functions(src), "method")
    # "def" starts at byte 13 (9 bytes "class C:\n" + 4 spaces)
    assert fn.def_start_offset == 13


def test_docstring_offsets_none_when_absent(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo():\n    pass\n")
    fn = extract_functions(src)[0]
    assert fn.docstring_start_offset is None
    assert fn.docstring_end_offset is None


def test_docstring_offsets_present(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text('def foo():\n    """Doc."""\n    pass\n')
    fn = extract_functions(src)[0]
    assert fn.docstring_start_offset is not None
    assert fn.docstring_end_offset is not None
    assert fn.docstring_end_offset > fn.docstring_start_offset
    # The slice should contain the docstring
    raw_bytes = src.read_bytes()
    slice_text = raw_bytes[fn.docstring_start_offset : fn.docstring_end_offset].decode()
    assert "Doc." in slice_text


def test_def_end_offset_points_to_body_start(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo():\n    pass\n")
    fn = extract_functions(src)[0]
    # def_end_offset should be byte offset of the first line of the body ("    pass")
    # line 2 starts at offset 11 (after "def foo():\n")
    assert fn.def_end_offset == 11


# ---------------------------------------------------------------------------
# Parameters — kinds
# ---------------------------------------------------------------------------


def test_no_params(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo(): pass\n")
    fn = extract_functions(src)[0]
    assert fn.parameters == ()


def test_positional_params(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo(a, b, c): pass\n")
    fn = extract_functions(src)[0]
    assert _params_of(fn) == [("a", "positional"), ("b", "positional"), ("c", "positional")]


def test_var_positional_and_var_keyword(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo(*args, **kwargs): pass\n")
    fn = extract_functions(src)[0]
    assert _params_of(fn) == [("args", "var_positional"), ("kwargs", "var_keyword")]


def test_keyword_only_after_star(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo(a, *, b, c): pass\n")
    fn = extract_functions(src)[0]
    assert _params_of(fn) == [
        ("a", "positional"),
        ("b", "keyword"),
        ("c", "keyword"),
    ]


def test_bound_parameter_on_method(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("class C:\n    def method(self, x): pass\n")
    fn = _fn(extract_functions(src), "method")
    assert _params_of(fn) == [("self", "bound"), ("x", "positional")]


def test_bound_parameter_on_classmethod(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("class C:\n    @classmethod\n    def cm(cls, x): pass\n")
    fn = _fn(extract_functions(src), "cm")
    assert _params_of(fn) == [("cls", "bound"), ("x", "positional")]


def test_staticmethod_no_bound_param(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("class C:\n    @staticmethod\n    def sm(x, y): pass\n")
    fn = _fn(extract_functions(src), "sm")
    assert _params_of(fn) == [("x", "positional"), ("y", "positional")]


def test_module_level_function_no_bound(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo(self): pass\n")
    fn = extract_functions(src)[0]
    # 'self' outside a class is just a regular positional param
    assert _params_of(fn) == [("self", "positional")]


# ---------------------------------------------------------------------------
# Parameters — annotations and defaults
# ---------------------------------------------------------------------------


def test_parameter_annotation(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo(x: int, y: str = 'hi') -> bool: pass\n")
    fn = extract_functions(src)[0]
    x, y = fn.parameters
    assert x.annotation == "int"
    assert x.default is None
    assert y.annotation == "str"
    assert y.default == "'hi'"


def test_return_annotation(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo(x: int) -> list[str]: pass\n")
    fn = extract_functions(src)[0]
    assert fn.return_annotation == "list[str]"


def test_no_return_annotation(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo(): pass\n")
    fn = extract_functions(src)[0]
    assert fn.return_annotation is None


def test_defaults_right_aligned(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo(a, b, c=1, d=2): pass\n")
    fn = extract_functions(src)[0]
    a, b, c, d = fn.parameters
    assert a.default is None
    assert b.default is None
    assert c.default == "1"
    assert d.default == "2"


def test_kwonly_default_and_none(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo(*, a, b=True): pass\n")
    fn = extract_functions(src)[0]
    a, b = fn.parameters
    assert a.kind == "keyword"
    assert a.default is None
    assert b.kind == "keyword"
    assert b.default == "True"


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def test_no_decorators(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo(): pass\n")
    fn = extract_functions(src)[0]
    assert fn.decorators == ()


def test_simple_decorator(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("@staticmethod\ndef foo(): pass\n")
    fn = extract_functions(src)[0]
    assert len(fn.decorators) == 1
    assert fn.decorators[0].name == "staticmethod"
    assert fn.decorators[0].arguments == {}


def test_dotted_decorator(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("@mcp.tool()\ndef foo(): pass\n")
    fn = extract_functions(src)[0]
    assert fn.decorators[0].name == "mcp.tool"


def test_decorator_with_kwargs(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text('@mcp.tool(description="A tool.")\ndef foo(): pass\n')
    fn = extract_functions(src)[0]
    dec = fn.decorators[0]
    assert dec.name == "mcp.tool"
    assert "description" in dec.arguments
    desc = dec.arguments["description"]
    assert "'A tool.'" in desc or '"A tool."' in desc


def test_multiple_decorators(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("@staticmethod\n@mcp.tool()\ndef foo(): pass\n")
    fn = extract_functions(src)[0]
    assert len(fn.decorators) == 2
    assert fn.decorators[0].name == "staticmethod"
    assert fn.decorators[1].name == "mcp.tool"


# ---------------------------------------------------------------------------
# Class membership
# ---------------------------------------------------------------------------


def test_method_containing_class(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("class MyClass:\n    def method(self): pass\n")
    fn = _fn(extract_functions(src), "method")
    assert fn.containing_class == "MyClass"


def test_module_level_no_class(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("def foo(): pass\n")
    fn = extract_functions(src)[0]
    assert fn.containing_class is None


def test_nested_function_not_a_method(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("class C:\n    def outer(self):\n        def inner(x): pass\n")
    inner = _fn(extract_functions(src), "inner")
    assert inner.containing_class is None


def test_nested_class_method_has_correct_class(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text("class Outer:\n    class Inner:\n        def method(self): pass\n")
    fn = _fn(extract_functions(src), "method")
    assert fn.containing_class == "Inner"


# ---------------------------------------------------------------------------
# Real fixture files
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_tier1_fixture_parses() -> None:
    fns = extract_functions(_FIXTURES / "tier1" / "simple_internal.py")
    names = {f.name for f in fns}
    assert "_normalize" in names
    assert "_compute" in names


def test_tier2_fixture_parse_expression() -> None:
    fns = extract_functions(_FIXTURES / "tier2" / "public_function.py")
    fn = _fn(fns, "parse_expression")
    assert fn.containing_class is None
    assert len(fn.parameters) == 2
    expr_p = fn.parameters[0]
    assert expr_p.name == "expression"
    assert expr_p.kind == "positional"
    strict_p = fn.parameters[1]
    assert strict_p.name == "strict"
    assert strict_p.default == "False"


def test_tier2_fixture_service_init_bound_param() -> None:
    fns = extract_functions(_FIXTURES / "tier2" / "public_function.py")
    init = _fn(fns, "__init__")
    assert init.containing_class == "PublicService"
    assert init.parameters[0].kind == "bound"
    assert init.parameters[0].name == "self"


def test_tier2_fixture_classmethod_bound(tmp_path: Path) -> None:
    fns = extract_functions(_FIXTURES / "tier2" / "public_function.py")
    cm = _fn(fns, "from_config")
    assert cm.parameters[0].kind == "bound"
    assert cm.parameters[0].name == "cls"


def test_tier2_fixture_staticmethod_no_bound() -> None:
    fns = extract_functions(_FIXTURES / "tier2" / "public_function.py")
    sm = _fn(fns, "validate")
    assert sm.parameters[0].kind == "positional"
    assert sm.parameters[0].name == "value"


def test_tier3_fixture_mcp_decorator() -> None:
    fns = extract_functions(_FIXTURES / "tier3" / "mcp_tool.py")
    fn = _fn(fns, "search_documents")
    assert any(d.name == "mcp.tool" for d in fn.decorators)


def test_tier3_fixture_decorator_description_kwarg() -> None:
    fns = extract_functions(_FIXTURES / "tier3" / "mcp_tool.py")
    fn = _fn(fns, "list_collections")
    dec = fn.decorators[0]
    assert dec.name == "mcp.tool"
    assert "description" in dec.arguments


def test_nested_fixture_inner_no_class() -> None:
    fns = extract_functions(_FIXTURES / "edge_cases" / "nested_functions.py")
    inner = _fn(fns, "inner_helper")
    assert inner.containing_class is None


def test_nested_fixture_inner_method_has_class() -> None:
    fns = extract_functions(_FIXTURES / "edge_cases" / "nested_functions.py")
    m = _fn(fns, "inner_method")
    assert m.containing_class == "Inner"


# ---------------------------------------------------------------------------
# parse_all_names
# ---------------------------------------------------------------------------


def test_parse_all_names_absent_returns_none() -> None:
    assert parse_all_names("def foo(): pass\n") is None


def test_parse_all_names_list_literal() -> None:
    src = '__all__ = ["foo", "bar"]\n'
    assert parse_all_names(src) == frozenset({"foo", "bar"})


def test_parse_all_names_tuple_literal() -> None:
    src = '__all__ = ("foo", "bar")\n'
    assert parse_all_names(src) == frozenset({"foo", "bar"})


def test_parse_all_names_empty_list() -> None:
    src = "__all__ = []\n"
    assert parse_all_names(src) == frozenset()


def test_parse_all_names_non_string_element_returns_none() -> None:
    # Cannot safely evaluate non-literal elements.
    src = "__all__ = ['foo', some_var]\n"
    assert parse_all_names(src) is None


def test_parse_all_names_concatenation_returns_none() -> None:
    src = '__all__ = ["foo"] + ["bar"]\n'
    assert parse_all_names(src) is None


def test_parse_all_names_inside_function_ignored() -> None:
    # __all__ inside a function body has no effect on importers and is ignored.
    src = 'def setup():\n    __all__ = ["foo"]\n'
    assert parse_all_names(src) is None


def test_parse_all_names_syntax_error_returns_none() -> None:
    assert parse_all_names("def (broken:") is None


# ---------------------------------------------------------------------------
# parse_tier_pragma
# ---------------------------------------------------------------------------


def test_parse_tier_pragma_absent_returns_none() -> None:
    assert parse_tier_pragma("def foo(): pass") is None


def test_parse_tier_pragma_tier1() -> None:
    assert parse_tier_pragma("def foo():  # docpact: tier=1") == 1


def test_parse_tier_pragma_tier3() -> None:
    assert parse_tier_pragma("def foo():  # docpact: tier=3") == 3


def test_parse_tier_pragma_tier4() -> None:
    assert parse_tier_pragma("def foo():  # docpact: tier=4") == 4


def test_parse_tier_pragma_extra_whitespace() -> None:
    assert parse_tier_pragma("def foo():  # docpact:  tier  =  2") == 2


def test_parse_tier_pragma_invalid_value_not_matched() -> None:
    # 5 is out of range 1-4; the pattern does not match it.
    assert parse_tier_pragma("def foo():  # docpact: tier=5") is None


def test_parse_tier_pragma_zero_not_matched() -> None:
    assert parse_tier_pragma("def foo():  # docpact: tier=0") is None


def test_parse_tier_pragma_in_middle_of_line() -> None:
    assert parse_tier_pragma("    async def handler(self):  # docpact: tier=3 -- MCP") == 3

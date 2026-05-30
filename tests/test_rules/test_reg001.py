"""Tests for REG001 — tool-registry schema names a parameter absent from the signature."""

from __future__ import annotations

from pathlib import Path

from docpact.model.diagnostic import Severity
from docpact.model.function_info import FunctionInfo, ParameterInfo
from docpact.model.tool_registry import ToolRegistryEntry
from docpact.rules._registry import RuleConfig
from docpact.rules.reg.reg001_schema_phantom_param import check_registry_phantom_params

_FILE = Path("bot_tools.py")


def _func(name: str, params: list[str], *, containing_class: str | None = None) -> FunctionInfo:
    """Build a minimal FunctionInfo with the given positional parameter names."""
    return FunctionInfo(
        name=name,
        file_path=_FILE,
        line=1,
        column=0,
        parameters=tuple(
            ParameterInfo(name=p, annotation=None, default=None, kind="positional") for p in params
        ),
        return_annotation=None,
        decorators=(),
        docstring_raw=None,
        docstring_line=1,
        containing_class=containing_class,
        def_start_offset=0,
        def_end_offset=0,
        docstring_start_offset=None,
        docstring_end_offset=None,
    )


def _entry(name: str, keys: frozenset[str] | None, line: int = 10) -> ToolRegistryEntry:
    """Build a registry entry with the given property keys."""
    return ToolRegistryEntry(
        name=name, line=line, column=4, property_keys=keys, has_description=True
    )


_CFG = RuleConfig(severity=Severity.ERROR, options={})


def test_phantom_param_fires() -> None:
    funcs = [_func("search", ["query"])]
    entries = [_entry("search", frozenset({"query", "limit"}))]
    results = check_registry_phantom_params(funcs, entries, _FILE, _CFG)
    assert len(results) == 1
    assert results[0].code == "REG001"
    assert "limit" in results[0].message
    assert "search" in results[0].message
    assert results[0].location.line == 10


def test_matching_schema_is_clean() -> None:
    funcs = [_func("search", ["query"])]
    entries = [_entry("search", frozenset({"query"}))]
    assert check_registry_phantom_params(funcs, entries, _FILE, _CFG) == []


def test_signature_param_missing_from_schema_does_not_fire() -> None:
    # REG001 is the phantom direction only; the reverse is REG003 (reserved).
    funcs = [_func("search", ["query", "limit"])]
    entries = [_entry("search", frozenset({"query"}))]
    assert check_registry_phantom_params(funcs, entries, _FILE, _CFG) == []


def test_dynamic_schema_skipped() -> None:
    funcs = [_func("search", ["query"])]
    entries = [_entry("search", None)]  # property_keys=None → not statically known
    assert check_registry_phantom_params(funcs, entries, _FILE, _CFG) == []


def test_unmatched_entry_not_reg001() -> None:
    # No function named "ghost" — that is REG002's concern, REG001 stays silent.
    funcs = [_func("search", ["query"])]
    entries = [_entry("ghost", frozenset({"query"}))]
    assert check_registry_phantom_params(funcs, entries, _FILE, _CFG) == []


def test_bound_receiver_not_a_valid_schema_param() -> None:
    # A method whose schema lists "self" should flag it as phantom.
    method = FunctionInfo(
        name="run",
        file_path=_FILE,
        line=1,
        column=0,
        parameters=(
            ParameterInfo(name="self", annotation=None, default=None, kind="bound"),
            ParameterInfo(name="x", annotation=None, default=None, kind="positional"),
        ),
        return_annotation=None,
        decorators=(),
        docstring_raw=None,
        docstring_line=1,
        containing_class=None,  # module-level def for correlation
        def_start_offset=0,
        def_end_offset=0,
        docstring_start_offset=None,
        docstring_end_offset=None,
    )
    entries = [_entry("run", frozenset({"self", "x"}))]
    results = check_registry_phantom_params([method], entries, _FILE, _CFG)
    assert len(results) == 1
    assert "self" in results[0].message


def test_method_not_correlated() -> None:
    # Registry entries name module-level functions; a same-named method is not matched.
    funcs = [_func("search", ["query"], containing_class="Tools")]
    entries = [_entry("search", frozenset({"phantom"}))]
    assert check_registry_phantom_params(funcs, entries, _FILE, _CFG) == []


def test_multiple_phantoms_sorted() -> None:
    funcs = [_func("f", ["a"])]
    entries = [_entry("f", frozenset({"z", "a", "m"}))]
    results = check_registry_phantom_params(funcs, entries, _FILE, _CFG)
    assert [r.message.split("documents parameter ")[1].split(",")[0] for r in results] == [
        "'m'",
        "'z'",
    ]


def test_empty_property_set_clean() -> None:
    funcs = [_func("f", ["a"])]
    entries = [_entry("f", frozenset())]
    assert check_registry_phantom_params(funcs, entries, _FILE, _CFG) == []

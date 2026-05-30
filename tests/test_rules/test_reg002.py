"""Tests for REG002 — tool-registry entry names no function in the same file."""

from __future__ import annotations

from pathlib import Path

from docpact.model.diagnostic import Severity
from docpact.model.function_info import FunctionInfo, ParameterInfo
from docpact.model.tool_registry import ToolRegistryEntry
from docpact.rules._registry import RuleConfig, all_rules
from docpact.rules.reg.reg002_unmatched_entry import check_unmatched_entries

_FILE = Path("bot_tools.py")


def _func(name: str, *, containing_class: str | None = None) -> FunctionInfo:
    """Build a minimal module-level FunctionInfo with the given name."""
    return FunctionInfo(
        name=name,
        file_path=_FILE,
        line=1,
        column=0,
        parameters=(ParameterInfo(name="x", annotation=None, default=None, kind="positional"),),
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


def _entry(name: str, line: int = 10) -> ToolRegistryEntry:
    """Build a registry entry referencing the given name."""
    return ToolRegistryEntry(
        name=name, line=line, column=4, property_keys=frozenset(), has_description=True
    )


_CFG = RuleConfig(severity=Severity.WARNING, options={})


def test_unmatched_entry_fires() -> None:
    results = check_unmatched_entries([_func("search")], [_entry("ghost")], _FILE, _CFG)
    assert len(results) == 1
    assert results[0].code == "REG002"
    assert "ghost" in results[0].message
    assert results[0].location.line == 10


def test_matched_entry_clean() -> None:
    assert check_unmatched_entries([_func("search")], [_entry("search")], _FILE, _CFG) == []


def test_method_does_not_satisfy_match() -> None:
    # Entries correlate to module-level functions; a same-named method does not count.
    funcs = [_func("search", containing_class="Tools")]
    results = check_unmatched_entries(funcs, [_entry("search")], _FILE, _CFG)
    assert len(results) == 1


def test_default_severity_is_off() -> None:
    # REG002 ships off by default (no INFO tier exists); opt in via severity override.
    meta, _ = all_rules()["REG002"]
    assert meta.default_severity == Severity.OFF


def test_results_sorted_by_location() -> None:
    entries = [_entry("b", line=20), _entry("a", line=10)]
    results = check_unmatched_entries([], entries, _FILE, _CFG)
    assert [r.location.line for r in results] == [10, 20]

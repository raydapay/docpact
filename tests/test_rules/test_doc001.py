"""Tests for DOC001 — missing docstring."""

from __future__ import annotations

from pathlib import Path

import docpact.rules.doc.doc001_missing_docstring  # noqa: F401 — triggers registration
from docpact.model.diagnostic import Severity
from docpact.parser.docstring import GoogleParser
from docpact.parser.source import extract_functions
from docpact.rules._registry import RuleConfig, all_rules

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _check(func_name: str, tier: int = 2) -> list:
    file_path = FIXTURES / "doc001_missing.py"
    fns = extract_functions(file_path)
    fn = next(f for f in fns if f.name == func_name)
    doc = GoogleParser().parse(fn.docstring_raw) if fn.docstring_raw else None
    meta, rule_fn = all_rules()["DOC001"]
    cfg = RuleConfig(severity=meta.default_severity, options={"tier": tier})
    return rule_fn(fn, doc, cfg)


# ---------------------------------------------------------------------------
# Positive: fires when docstring is absent
# ---------------------------------------------------------------------------


def test_fires_on_public_function_missing_docstring() -> None:
    results = _check("public_no_doc")
    assert len(results) == 1
    assert results[0].code == "DOC001"
    assert results[0].severity == Severity.ERROR


def test_message_contains_tier_label() -> None:
    results = _check("public_no_doc", tier=2)
    assert "Tier 2" in results[0].message


def test_fires_on_method_missing_docstring() -> None:
    file_path = FIXTURES / "doc001_missing.py"
    fns = extract_functions(file_path)
    fn = next(f for f in fns if f.name == "method_no_doc")
    meta, rule_fn = all_rules()["DOC001"]
    cfg = RuleConfig(severity=meta.default_severity, options={"tier": 2})
    results = rule_fn(fn, None, cfg)
    assert len(results) == 1


def test_fires_on_private_function_at_tier1() -> None:
    results = _check("_private_no_doc", tier=1)
    assert len(results) == 1


# ---------------------------------------------------------------------------
# Negative: does not fire when docstring is present
# ---------------------------------------------------------------------------


def test_no_fire_when_docstring_present() -> None:
    results = _check("public_with_doc")
    assert results == []


def test_no_fire_when_method_has_docstring() -> None:
    file_path = FIXTURES / "doc001_missing.py"
    fns = extract_functions(file_path)
    fn = next(f for f in fns if f.name == "method_with_doc")
    doc = GoogleParser().parse(fn.docstring_raw) if fn.docstring_raw else None
    meta, rule_fn = all_rules()["DOC001"]
    cfg = RuleConfig(severity=meta.default_severity, options={"tier": 2})
    assert rule_fn(fn, doc, cfg) == []


# ---------------------------------------------------------------------------
# Fix behavior
# ---------------------------------------------------------------------------


def test_fix_is_attached() -> None:
    results = _check("public_no_doc")
    assert results[0].fix is not None


def test_fix_is_at_def_end_offset(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> str:\n    pass\n")
    fns = extract_functions(src)
    fn = fns[0]
    meta, rule_fn = all_rules()["DOC001"]
    cfg = RuleConfig(severity=meta.default_severity, options={"tier": 2})
    results = rule_fn(fn, None, cfg)
    assert results[0].fix is not None
    assert results[0].fix.start_offset == fn.def_end_offset
    assert results[0].fix.end_offset == fn.def_end_offset


def test_fix_stub_contains_fill_marker(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> str:\n    pass\n")
    fns = extract_functions(src)
    fn = fns[0]
    meta, rule_fn = all_rules()["DOC001"]
    cfg = RuleConfig(severity=meta.default_severity, options={"tier": 2})
    results = rule_fn(fn, None, cfg)
    assert "[FILL" in results[0].fix.replacement  # type: ignore[union-attr]


def test_tier1_stub_is_single_line(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def _foo(x: int) -> str:\n    pass\n")
    fns = extract_functions(src)
    fn = fns[0]
    meta, rule_fn = all_rules()["DOC001"]
    cfg = RuleConfig(severity=meta.default_severity, options={"tier": 1})
    results = rule_fn(fn, None, cfg)
    replacement = results[0].fix.replacement  # type: ignore[union-attr]
    assert '"""' in replacement
    assert "Args:" not in replacement


def test_tier2_stub_includes_args_section(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int, y: str) -> bool:\n    pass\n")
    fns = extract_functions(src)
    fn = fns[0]
    meta, rule_fn = all_rules()["DOC001"]
    cfg = RuleConfig(severity=meta.default_severity, options={"tier": 2})
    results = rule_fn(fn, None, cfg)
    replacement = results[0].fix.replacement  # type: ignore[union-attr]
    assert "Args:" in replacement
    assert "x:" in replacement
    assert "y:" in replacement


def test_tier2_stub_includes_returns_when_annotated(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> str:\n    pass\n")
    fns = extract_functions(src)
    fn = fns[0]
    meta, rule_fn = all_rules()["DOC001"]
    cfg = RuleConfig(severity=meta.default_severity, options={"tier": 2})
    results = rule_fn(fn, None, cfg)
    replacement = results[0].fix.replacement  # type: ignore[union-attr]
    assert "Returns:" in replacement


def test_tier2_stub_omits_returns_for_none(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")
    fns = extract_functions(src)
    fn = fns[0]
    meta, rule_fn = all_rules()["DOC001"]
    cfg = RuleConfig(severity=meta.default_severity, options={"tier": 2})
    results = rule_fn(fn, None, cfg)
    replacement = results[0].fix.replacement  # type: ignore[union-attr]
    assert "Returns:" not in replacement


def test_tier3_stub_includes_mcp_section(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> str:\n    pass\n")
    fns = extract_functions(src)
    fn = fns[0]
    meta, rule_fn = all_rules()["DOC001"]
    cfg = RuleConfig(severity=meta.default_severity, options={"tier": 3})
    results = rule_fn(fn, None, cfg)
    replacement = results[0].fix.replacement  # type: ignore[union-attr]
    assert "MCP:" in replacement
    assert "Raises:" in replacement
    assert "Constraints:" in replacement


def test_stub_excludes_self_from_args(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("class C:\n    def method(self, x: int) -> None:\n        pass\n")
    fns = extract_functions(src)
    fn = next(f for f in fns if f.name == "method")
    meta, rule_fn = all_rules()["DOC001"]
    cfg = RuleConfig(severity=meta.default_severity, options={"tier": 2})
    results = rule_fn(fn, None, cfg)
    replacement = results[0].fix.replacement  # type: ignore[union-attr]
    assert "self:" not in replacement
    assert "x:" in replacement


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------


def test_location_points_to_function_line(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")
    fns = extract_functions(src)
    fn = fns[0]
    meta, rule_fn = all_rules()["DOC001"]
    cfg = RuleConfig(severity=meta.default_severity, options={"tier": 2})
    results = rule_fn(fn, None, cfg)
    assert results[0].location.line == 1
    assert results[0].location.column == 0

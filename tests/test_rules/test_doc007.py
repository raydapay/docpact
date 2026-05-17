"""Tests for DOC007 — Args section inconsistent with function signature."""

from __future__ import annotations

from pathlib import Path

import docpact.rules.doc.doc007_param_mismatch  # noqa: F401 — triggers registration
from docpact.model.diagnostic import Severity
from docpact.parser.docstring import GoogleParser
from docpact.parser.source import extract_functions
from docpact.rules._registry import RuleConfig, all_rules

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _check(func_name: str, tier: int = 2) -> list:
    file_path = FIXTURES / "doc007_mismatch.py"
    fns = extract_functions(file_path)
    fn = next(f for f in fns if f.name == func_name)
    doc = GoogleParser().parse(fn.docstring_raw) if fn.docstring_raw else None
    meta, rule_fn = all_rules()["DOC007"]
    cfg = RuleConfig(severity=meta.default_severity, options={"tier": tier})
    return rule_fn(fn, doc, cfg)


# ---------------------------------------------------------------------------
# No fire cases
# ---------------------------------------------------------------------------


def test_no_fire_when_doc_is_none() -> None:
    file_path = FIXTURES / "doc007_mismatch.py"
    fns = extract_functions(file_path)
    fn = next(f for f in fns if f.name == "correct_args")
    meta, rule_fn = all_rules()["DOC007"]
    cfg = RuleConfig(severity=meta.default_severity, options={"tier": 2})
    assert rule_fn(fn, None, cfg) == []


def test_no_fire_when_no_args_section() -> None:
    results = _check("no_args_section")
    assert results == []


def test_no_fire_on_correct_args(tmp_path: Path) -> None:
    results = _check("correct_args")
    assert results == []


def test_no_fire_varargs_not_documented(tmp_path: Path) -> None:
    # *args and **kwargs are optional — not documenting them is fine.
    results = _check("varargs_not_required")
    assert results == []


def test_no_fire_empty_args_at_tier1() -> None:
    # At Tier 1, missing positional params from Args is not an error.
    results = _check("param_in_sig_absent_from_args", tier=1)
    # Sub-case 1 only fires at tier >= 2. Sub-case 2 doesn't apply here.
    codes = [r.code for r in results]
    # No phantom params in this fixture, so no results at tier 1.
    assert codes == []


# ---------------------------------------------------------------------------
# Sub-case 1: param in sig absent from Args (tier >= 2 only)
# ---------------------------------------------------------------------------


def test_fires_for_missing_required_param_tier2() -> None:
    results = _check("param_in_sig_absent_from_args", tier=2)
    assert len(results) == 1
    assert results[0].code == "DOC007"
    assert "absent from Args" in results[0].message
    assert "'y'" in results[0].message


def test_missing_param_is_error_severity() -> None:
    results = _check("param_in_sig_absent_from_args", tier=2)
    assert results[0].severity == Severity.ERROR


def test_missing_param_no_fire_at_tier1() -> None:
    results = _check("param_in_sig_absent_from_args", tier=1)
    assert results == []


# ---------------------------------------------------------------------------
# Sub-case 2: phantom param in Args (all tiers)
# ---------------------------------------------------------------------------


def test_fires_for_phantom_param() -> None:
    results = _check("phantom_param_in_args", tier=2)
    assert len(results) == 1
    assert "absent from signature" in results[0].message
    assert "'ghost'" in results[0].message


def test_phantom_fires_at_tier1() -> None:
    results = _check("phantom_param_in_args", tier=1)
    assert len(results) == 1
    assert "absent from signature" in results[0].message


def test_phantom_fires_at_tier3() -> None:
    results = _check("phantom_param_in_args", tier=3)
    assert len(results) == 1


# ---------------------------------------------------------------------------
# Both sub-cases in same function
# ---------------------------------------------------------------------------


def test_both_subcases_fire() -> None:
    results = _check("both_mismatches", tier=2)
    messages = [r.message for r in results]
    assert any("absent from Args" in m for m in messages)
    assert any("absent from signature" in m for m in messages)
    assert len(results) == 2


# ---------------------------------------------------------------------------
# No fix available
# ---------------------------------------------------------------------------


def test_no_fix_attached() -> None:
    results = _check("param_in_sig_absent_from_args")
    for r in results:
        assert r.fix is None
        assert r.unsafe_fix is None


# ---------------------------------------------------------------------------
# Empty Args (None.) form
# ---------------------------------------------------------------------------


def test_empty_args_none_form_with_phantom() -> None:
    # "Args:\n    None." documents nothing, so no phantom; but sig has a param.
    # At tier 2, the required param 'x' is absent from Args → fires.
    results = _check("empty_args_none", tier=2)
    codes = [r.code for r in results]
    assert "DOC007" in codes
    # The absent param is 'x'
    assert any("'x'" in r.message for r in results)


# ---------------------------------------------------------------------------
# Varargs documented with * / ** prefix
# ---------------------------------------------------------------------------


def test_varargs_documented_with_star_prefix_is_valid(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text(
        "def foo(x: int, *args: str) -> None:\n"
        '    """Do something.\n\n'
        "    Args:\n"
        "        x: Required.\n"
        "        *args: Extra strings.\n"
        '    """\n'
    )
    fns = extract_functions(src)
    fn = fns[0]
    doc = GoogleParser().parse(fn.docstring_raw)
    meta, rule_fn = all_rules()["DOC007"]
    cfg = RuleConfig(severity=meta.default_severity, options={"tier": 2})
    results = rule_fn(fn, doc, cfg)
    # *args is valid to document; no phantom
    assert results == []


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------


def test_location_points_to_function_definition(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text(
        "def foo(x: int, y: str) -> None:\n"
        '    """Do something.\n\n'
        "    Args:\n"
        "        x: Only x.\n"
        '    """\n'
    )
    fns = extract_functions(src)
    fn = fns[0]
    doc = GoogleParser().parse(fn.docstring_raw)
    meta, rule_fn = all_rules()["DOC007"]
    cfg = RuleConfig(severity=meta.default_severity, options={"tier": 2})
    results = rule_fn(fn, doc, cfg)
    assert results[0].location.line == 1
    assert results[0].location.column == 0

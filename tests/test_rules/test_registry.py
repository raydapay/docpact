"""Tests for docpact.rules._registry and load_builtin_rules."""

from __future__ import annotations

import pytest

from docpact.model.diagnostic import Severity
from docpact.rules import load_builtin_rules
from docpact.rules._registry import RuleConfig, RuleMetadata, all_rules, register

# ---------------------------------------------------------------------------
# Ensure all built-in rules are loaded before tests that inspect the registry.
# ---------------------------------------------------------------------------

load_builtin_rules()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_CODE = "_REGISTRY_TEST_DUP"


def _test_meta(code: str) -> RuleMetadata:
    return RuleMetadata(
        code=code,
        namespace="TST",
        summary="test rule",
        default_severity=Severity.WARNING,
        fixable=False,
        unsafe_fixable=False,
    )


# ---------------------------------------------------------------------------
# load_builtin_rules — all expected codes present
# ---------------------------------------------------------------------------


def test_all_builtin_rules_registered() -> None:
    rules = all_rules()
    expected = {
        "DOC001",
        "DOC002",
        "DOC003",
        "DOC007",
        "DOC012",
        "DOC013",
        "DOC014",
        "DOC050",
        "DOC098",
        "DOC099",
        "FIX001",
        "FIX002",
        "MCP001",
        "TY001",
        "TY002",
    }
    missing = expected - rules.keys()
    assert not missing, f"Rules not registered: {sorted(missing)}"


def test_load_builtin_rules_is_idempotent() -> None:
    before = set(all_rules().keys())
    load_builtin_rules()
    load_builtin_rules()
    assert set(all_rules().keys()) == before


# ---------------------------------------------------------------------------
# Basic registration
# ---------------------------------------------------------------------------


def test_all_rules_returns_dict_copy() -> None:
    rules = all_rules()
    rules.clear()
    assert "DOC001" in all_rules()


def test_doc001_metadata() -> None:
    meta, fn = all_rules()["DOC001"]
    assert meta.code == "DOC001"
    assert meta.namespace == "DOC"
    assert meta.default_severity == Severity.ERROR
    assert meta.fixable is True
    assert meta.unsafe_fixable is False
    assert callable(fn)


def test_mcp001_metadata() -> None:
    meta, _ = all_rules()["MCP001"]
    assert meta.code == "MCP001"
    assert meta.namespace == "MCP"
    assert meta.fixable is False
    assert meta.unsafe_fixable is False


def test_ty001_metadata() -> None:
    meta, _ = all_rules()["TY001"]
    assert meta.code == "TY001"
    assert meta.namespace == "TY"
    assert meta.default_severity == Severity.ERROR
    assert meta.fixable is False


def test_ty002_metadata() -> None:
    meta, _ = all_rules()["TY002"]
    assert meta.code == "TY002"
    assert meta.namespace == "TY"
    assert meta.default_severity == Severity.WARNING
    assert meta.fixable is False


def test_doc013_is_fixable() -> None:
    meta, _ = all_rules()["DOC013"]
    assert meta.fixable is True


# ---------------------------------------------------------------------------
# Duplicate registration raises
# ---------------------------------------------------------------------------


def test_register_and_duplicate_raises() -> None:
    @register(_test_meta(_TEST_CODE))
    def _first(func, doc, config):  # type: ignore[misc]
        return []

    assert _TEST_CODE in all_rules()

    with pytest.raises(ValueError, match="already registered"):

        @register(_test_meta(_TEST_CODE))
        def _second(func, doc, config):  # type: ignore[misc]
            return []


# ---------------------------------------------------------------------------
# RuleConfig
# ---------------------------------------------------------------------------


def test_rule_config_defaults() -> None:
    cfg = RuleConfig(severity=Severity.ERROR, options={})
    assert cfg.severity == Severity.ERROR
    assert cfg.options == {}


def test_rule_config_is_frozen() -> None:
    cfg = RuleConfig(severity=Severity.ERROR, options={})
    with pytest.raises((AttributeError, TypeError)):
        cfg.severity = Severity.WARNING  # type: ignore[misc]


def test_every_registered_rule_is_loaded() -> None:
    """Every @register'd rule file must be imported by load_builtin_rules().

    Guards against the DOC052 class of bug: a rule file declares a code via
    @register but the import is forgotten in load_builtin_rules(), so the rule
    is inert in real `docpact check` runs while its own tests (which import the
    module directly) still pass.
    """
    import re
    from pathlib import Path

    import docpact.rules as rules_pkg

    load_builtin_rules()
    loaded = set(all_rules())

    rules_dir = Path(rules_pkg.__file__).parent
    declared: set[str] = set()
    for f in rules_dir.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        if "@register" not in text:
            continue
        declared.update(re.findall(r'code="([A-Z]+[0-9]+)"', text))

    missing = declared - loaded
    assert not missing, (
        f"Rule files declare codes that load_builtin_rules() does not import "
        f"(inert in production): {sorted(missing)}"
    )

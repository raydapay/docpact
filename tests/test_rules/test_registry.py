"""Tests for docpact.rules._registry — registration and lookup."""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Fixtures: import stub rule modules to trigger self-registration.
# The stub functions raise NotImplementedError — that is intentional and
# does not affect registry tests, which only exercise metadata and dispatch.
# ---------------------------------------------------------------------------
import docpact.rules.doc.doc001_missing_docstring
import docpact.rules.doc.doc007_param_mismatch
import docpact.rules.mcp.mcp001_decorator_docstring_conflict  # noqa: F401
from docpact.model.diagnostic import Severity
from docpact.rules._registry import RuleConfig, RuleMetadata, all_rules, register

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
# Basic registration
# ---------------------------------------------------------------------------


def test_stub_rules_are_registered() -> None:
    rules = all_rules()
    assert "DOC001" in rules
    assert "DOC007" in rules
    assert "MCP001" in rules


def test_all_rules_returns_dict_copy() -> None:
    # Mutating the returned dict must not affect the registry.
    rules = all_rules()
    rules.clear()
    assert "DOC001" in all_rules()


def test_rule_metadata_fields() -> None:
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


# ---------------------------------------------------------------------------
# Duplicate registration raises
# ---------------------------------------------------------------------------


def test_register_and_duplicate_raises() -> None:
    # Register a unique test code once — succeeds.
    @register(_test_meta(_TEST_CODE))
    def _first(func, doc, config):  # type: ignore[misc]
        return []

    assert _TEST_CODE in all_rules()

    # Registering the same code a second time must raise.
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

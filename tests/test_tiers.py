"""Tests for docpact.tiers — assign_tier."""

from __future__ import annotations

from pathlib import Path

import pytest

from docpact.model.function_info import DecoratorInfo, FunctionInfo
from docpact.tiers import MCP_DECORATORS, assign_tier

_DEFAULT_PATH = Path("/project/src/module.py")


def _fn(
    name: str = "foo",
    *,
    containing_class: str | None = None,
    decorators: tuple[DecoratorInfo, ...] = (),
    file_path: Path = _DEFAULT_PATH,
) -> FunctionInfo:
    return FunctionInfo(
        name=name,
        file_path=file_path,
        line=1,
        column=0,
        parameters=(),
        return_annotation=None,
        decorators=decorators,
        docstring_raw=None,
        docstring_line=0,
        containing_class=containing_class,
        def_start_offset=0,
        def_end_offset=10,
        docstring_start_offset=None,
        docstring_end_offset=None,
    )


def _dec(name: str) -> DecoratorInfo:
    return DecoratorInfo(name=name)


# ---------------------------------------------------------------------------
# Rule 1 — MCP decorators → Tier 3
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("decorator", sorted(MCP_DECORATORS))
def test_mcp_decorator_is_tier3(decorator: str) -> None:
    fn = _fn("my_tool", decorators=(_dec(decorator),))
    assert assign_tier(fn) == 3


def test_mcp_tool_on_private_class_still_tier3() -> None:
    # Rule 1 fires before rule 3.
    fn = _fn("my_tool", containing_class="_Internal", decorators=(_dec("mcp.tool"),))
    assert assign_tier(fn) == 3


def test_mcp_tool_on_private_name_still_tier3() -> None:
    # Rule 1 fires before rule 4.
    fn = _fn("_private_tool", decorators=(_dec("mcp.tool"),))
    assert assign_tier(fn) == 3


# ---------------------------------------------------------------------------
# Rule 2 — Explicit tier override via configuration
# ---------------------------------------------------------------------------


def test_tier_override_exact_relative_pattern() -> None:
    fn = _fn(file_path=Path("/project/src/routes.py"))
    assert assign_tier(fn, tier_overrides={"src/routes.py": 4}) == 4


def test_tier_override_glob_wildcard() -> None:
    fn = _fn(file_path=Path("/project/src/api/routes.py"))
    assert assign_tier(fn, tier_overrides={"src/*.py": 4}) == 4


def test_tier_override_full_absolute_path() -> None:
    fn = _fn(file_path=Path("/project/src/routes.py"))
    assert assign_tier(fn, tier_overrides={"/project/src/routes.py": 4}) == 4


def test_tier_override_no_match() -> None:
    fn = _fn(file_path=Path("/project/src/module.py"))
    assert assign_tier(fn, tier_overrides={"src/routes.py": 4}) == 2


def test_tier_override_none() -> None:
    fn = _fn()
    assert assign_tier(fn, tier_overrides=None) == 2


def test_tier_override_can_force_tier1() -> None:
    fn = _fn("public_fn", file_path=Path("/project/src/internal.py"))
    assert assign_tier(fn, tier_overrides={"src/internal.py": 1}) == 1


def test_mcp_decorator_beats_tier4_override() -> None:
    # Rule 1 is evaluated before rule 2.
    fn = _fn("handler", decorators=(_dec("mcp.tool"),), file_path=Path("/project/src/routes.py"))
    assert assign_tier(fn, tier_overrides={"src/routes.py": 4}) == 3


# ---------------------------------------------------------------------------
# Rule 3 — Method on class whose name begins with `_` → Tier 1
# ---------------------------------------------------------------------------


def test_method_on_private_class_is_tier1() -> None:
    fn = _fn("method", containing_class="_Internal")
    assert assign_tier(fn) == 1


def test_method_on_dunder_prefixed_class_is_tier1() -> None:
    # Double-underscore class names are still private.
    fn = _fn("method", containing_class="__VeryPrivate")
    assert assign_tier(fn) == 1


def test_method_on_public_class_is_tier2() -> None:
    fn = _fn("method", containing_class="PublicService")
    assert assign_tier(fn) == 2


# ---------------------------------------------------------------------------
# Rule 4 — Name begins with `_` (not a dunder) → Tier 1
# ---------------------------------------------------------------------------


def test_single_underscore_function_is_tier1() -> None:
    fn = _fn("_helper")
    assert assign_tier(fn) == 1


def test_single_underscore_method_is_tier1() -> None:
    fn = _fn("_validate", containing_class="Service")
    assert assign_tier(fn) == 1


def test_double_underscore_prefix_no_suffix_is_tier1() -> None:
    # __mangled has no trailing __ — not a dunder, caught by rule 4.
    fn = _fn("__mangled", containing_class="Service")
    assert assign_tier(fn) == 1


def test_self_as_function_name_is_not_private() -> None:
    # "self" starts with no underscore — just a regular name.
    fn = _fn("self")
    assert assign_tier(fn) == 2


# ---------------------------------------------------------------------------
# Rule 5 — Dunder methods inherit tier of containing class
# ---------------------------------------------------------------------------


def test_init_on_public_class_is_tier2() -> None:
    fn = _fn("__init__", containing_class="Service")
    assert assign_tier(fn) == 2


def test_repr_on_public_class_is_tier2() -> None:
    fn = _fn("__repr__", containing_class="Service")
    assert assign_tier(fn) == 2


def test_dunder_on_private_class_is_tier1_via_rule3() -> None:
    # Rule 3 fires before rule 5: the class name starts with `_`.
    fn = _fn("__init__", containing_class="_Internal")
    assert assign_tier(fn) == 1


def test_module_level_dunder_is_tier2() -> None:
    # No containing class — unusual but valid (e.g., module-level __getattr__).
    fn = _fn("__getattr__")
    assert assign_tier(fn) == 2


@pytest.mark.parametrize(
    "name",
    ["__init__", "__repr__", "__eq__", "__str__", "__len__", "__call__"],
)
def test_common_dunders_on_public_class_are_tier2(name: str) -> None:
    fn = _fn(name, containing_class="MyClass")
    assert assign_tier(fn) == 2


# ---------------------------------------------------------------------------
# Rule 6 — Property / classmethod / staticmethod inherit class tier
# ---------------------------------------------------------------------------


def test_property_on_public_class_is_tier2() -> None:
    fn = _fn("value", containing_class="Config", decorators=(_dec("property"),))
    assert assign_tier(fn) == 2


def test_classmethod_on_public_class_is_tier2() -> None:
    fn = _fn("from_config", containing_class="Service", decorators=(_dec("classmethod"),))
    assert assign_tier(fn) == 2


def test_staticmethod_on_public_class_is_tier2() -> None:
    fn = _fn("validate", containing_class="Service", decorators=(_dec("staticmethod"),))
    assert assign_tier(fn) == 2


def test_property_on_private_class_is_tier1_via_rule3() -> None:
    # Rule 3 fires before we reach the implicit rule 6 / rule 7.
    fn = _fn("value", containing_class="_Config", decorators=(_dec("property"),))
    assert assign_tier(fn) == 1


def test_cached_property_on_public_class_is_tier2() -> None:
    fn = _fn("expensive", containing_class="Service", decorators=(_dec("cached_property"),))
    assert assign_tier(fn) == 2


# ---------------------------------------------------------------------------
# Rule 7 — All other public functions and methods → Tier 2
# ---------------------------------------------------------------------------


def test_plain_public_function_is_tier2() -> None:
    fn = _fn("process")
    assert assign_tier(fn) == 2


def test_plain_public_method_is_tier2() -> None:
    fn = _fn("process", containing_class="Service")
    assert assign_tier(fn) == 2


def test_annotated_public_function_is_tier2() -> None:
    fn = _fn(
        "parse",
        decorators=(),
        containing_class=None,
    )
    assert assign_tier(fn) == 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_no_decorators_no_class_public_name_is_tier2() -> None:
    fn = _fn("transform")
    assert assign_tier(fn) == 2


def test_tier_overrides_empty_dict_is_ignored() -> None:
    fn = _fn("transform")
    assert assign_tier(fn, tier_overrides={}) == 2


def test_private_function_in_private_class_is_tier1() -> None:
    # Both rule 3 and rule 4 would fire; rule 3 wins (evaluated first).
    fn = _fn("_helper", containing_class="_Internal")
    assert assign_tier(fn) == 1

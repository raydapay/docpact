"""Tier assignment.

Implements the deterministic rules in spec §10.1. Tier assignment is the
first operation the rule engine performs; it determines which rules
apply to each function.

See ADR-003 for the rationale behind context-based assignment.
"""

from __future__ import annotations

import fnmatch
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from docpact.model.function_info import FunctionInfo


# Decorator names that trigger Tier 3. See spec §10.1 rule 1.
MCP_DECORATORS: frozenset[str] = frozenset(
    {
        "mcp.tool",
        "mcp.resource",
        "mcp.prompt",
    }
)


def _is_dunder(name: str) -> bool:
    """Return True if name is a dunder method (__init__, __repr__, etc.)."""
    return (
        name.startswith("__") and name.endswith("__") and len(name) > 4  # excludes bare `____`
    )


def _class_is_private(class_name: str) -> bool:
    """Return True if the class name begins with an underscore."""
    return class_name.startswith("_")


def assign_tier(
    func: FunctionInfo,
    tier_overrides: dict[str, int] | None = None,
    *,
    all_names: frozenset[str] | None = None,
    registered_tool_names: frozenset[str] | None = None,
    root: Path | None = None,
) -> int:
    """Determine the tier of a function.

    Rules are evaluated in order; the first match wins (spec §10.1). A Tier 3
    floor from tool-registry membership is then applied on top of the result.

    Args:
        func: The function metadata.
        tier_overrides: Optional per-file tier overrides from configuration.
            Keys are fnmatch glob patterns relative to the project root;
            values are tier numbers 1-4.
        all_names: Names exported by __all__ in the function's module, or
            None if the module does not define __all__. When provided, this
            is the authoritative visibility contract for module-level functions
            (not for methods, which are accessed through their class).
        registered_tool_names: Names of module-level functions registered as
            tools by a same-file registry entry (ADR-005). A module-level
            function in this set is held to a Tier 3 floor: its tier becomes
            ``max(3, t)``. The caller is responsible for omitting names where
            the floor is disabled (``assign_tier = false`` or ``no_tier_floor``).
        root: Project root directory used to anchor glob patterns. When
            provided, patterns are matched against the path relative to root
            before falling back to absolute-path matching.

    Returns:
        Tier number, 1-4.

    Constraints:
        Deterministic. The same input always produces the same output.
        No global state is consulted.

    Stability: stable
    """
    base = _assign_base_tier(func, tier_overrides, all_names=all_names, root=root)
    # Tier 3 floor from tool-registry membership. A registry entry is the
    # data-structure equivalent of @mcp.tool; the floor is a minimum, not a
    # fixed value, so a per-file-tier=4 can still raise above it (ADR-005).
    if (
        registered_tool_names is not None
        and func.containing_class is None
        and func.name in registered_tool_names
    ):
        return max(3, base)
    return base


def _assign_base_tier(
    func: FunctionInfo,
    tier_overrides: dict[str, int] | None,
    *,
    all_names: frozenset[str] | None,
    root: Path | None,
) -> int:
    """Assign a tier from the ordered context rules, before any registry floor."""
    # Rule 1: MCP decorators → Tier 3.
    if any(d.name in MCP_DECORATORS for d in func.decorators):
        return 3

    # Rule 2: Explicit file-level tier override from configuration.
    if tier_overrides:
        abs_str = func.file_path.as_posix()
        try:
            rel_str = func.file_path.relative_to(root).as_posix() if root else abs_str
        except ValueError:
            rel_str = abs_str
        for pattern, tier_num in tier_overrides.items():
            if (
                fnmatch.fnmatch(rel_str, pattern)
                or fnmatch.fnmatch(abs_str, pattern)
                or fnmatch.fnmatch(abs_str, f"*/{pattern}")
            ):
                return tier_num

    # Rule 3: __all__ is the definitive public API contract for module-level
    # functions. Methods are accessed through their class and are unaffected.
    if all_names is not None and func.containing_class is None:
        return 2 if func.name in all_names else 1

    # Rule 4: Method on a class whose name begins with `_` → Tier 1.
    if func.containing_class is not None and _class_is_private(func.containing_class):
        return 1

    # Rule 5: Name begins with `_` (other than dunder methods) → Tier 1.
    if func.name.startswith("_") and not _is_dunder(func.name):
        return 1

    # Rule 6: Dunder methods inherit the tier of their containing class.
    # Rule 4 already handles the private-class case, so here the class is
    # either public or absent (module-level dunder, unusual but possible).
    # Both cases yield Tier 2.
    if _is_dunder(func.name):
        return 2

    # Rule 7: @property, @cached_property, @staticmethod, @classmethod inherit
    # the tier of their containing class. Rules 4 and 8 already produce the
    # correct result without a special case here.

    # Rule 8: All other public functions and methods → Tier 2.
    return 2

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
    return class_name.startswith("_")


def assign_tier(func: FunctionInfo, tier_overrides: dict[str, int] | None = None) -> int:
    """Determine the tier of a function.

    Rules are evaluated in order; the first match wins (spec §10.1).

    Args:
        func: The function metadata.
        tier_overrides: Optional per-file tier overrides from configuration.
            Keys are fnmatch glob patterns relative to the project root;
            values are tier numbers 1-4.

    Returns:
        Tier number, 1-4.

    Constraints:
        Deterministic. The same input always produces the same output.
        No global state is consulted.

    Stability: stable
    """
    # Rule 1: MCP decorators → Tier 3.
    if any(d.name in MCP_DECORATORS for d in func.decorators):
        return 3

    # Rule 2: Explicit file-level tier override from configuration.
    if tier_overrides:
        path_str = str(func.file_path)
        for pattern, tier_num in tier_overrides.items():
            # Match against the full path or with a leading wildcard so that
            # relative patterns like "src/routes.py" match absolute paths.
            if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(path_str, f"*/{pattern}"):
                return tier_num

    # Rule 3: Method on a class whose name begins with `_` → Tier 1.
    if func.containing_class is not None and _class_is_private(func.containing_class):
        return 1

    # Rule 4: Name begins with `_` (other than dunder methods) → Tier 1.
    if func.name.startswith("_") and not _is_dunder(func.name):
        return 1

    # Rule 5: Dunder methods inherit the tier of their containing class.
    # Rule 3 already handles the private-class case, so here the class is
    # either public or absent (module-level dunder, unusual but possible).
    # Both cases yield Tier 2.
    if _is_dunder(func.name):
        return 2

    # Rule 6: @property, @cached_property, @staticmethod, @classmethod inherit
    # the tier of their containing class. Rules 3 and 7 already produce the
    # correct result without a special case here.

    # Rule 7: All other public functions and methods → Tier 2.
    return 2

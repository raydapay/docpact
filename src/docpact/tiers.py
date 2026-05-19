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
    root: Path | None = None,
) -> int:
    """Determine the tier of a function.

    Rules are evaluated in order; the first match wins (spec §10.1).

    Args:
        func: The function metadata.
        tier_overrides: Optional per-file tier overrides from configuration.
            Keys are fnmatch glob patterns relative to the project root;
            values are tier numbers 1-4.
        all_names: Names exported by __all__ in the function's module, or
            None if the module does not define __all__. When provided, this
            is the authoritative visibility contract for module-level functions
            (not for methods, which are accessed through their class).
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
    # Rule 1: MCP decorators → Tier 3.
    if any(d.name in MCP_DECORATORS for d in func.decorators):
        return 3

    # Rule 2: Explicit file-level tier override from configuration.
    if tier_overrides:
        abs_str = str(func.file_path)
        try:
            rel_str = str(func.file_path.relative_to(root)) if root else abs_str
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

"""Tier assignment.

Implements the deterministic rules in spec §10.1. Tier assignment is the
first operation the rule engine performs; it determines which rules
apply to each function.

See ADR-003 for the rationale behind context-based assignment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo


def assign_tier(func: FunctionInfo, tier_overrides: dict[str, int] | None = None) -> int:
    """Determine the tier of a function.

    Args:
        func: The function metadata.
        tier_overrides: Optional per-file tier overrides from configuration.
            Keys are glob patterns; values are tier numbers 1-4.

    Returns:
        Tier number, 1-4.

    Constraints:
        Deterministic. The same input produces the same output on every
        invocation. No global state is consulted.

    Stability: stable
    """
    raise NotImplementedError("tier assignment not yet implemented")


# Decorator names that trigger Tier 3.
# See spec §10.1 rule 1.
MCP_DECORATORS = frozenset(
    {
        "mcp.tool",
        "mcp.resource",
        "mcp.prompt",
    }
)

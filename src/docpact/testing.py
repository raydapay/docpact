"""Public testing API — for use in project test suites.

This module is the v0.1 public surface for programmatic assertions
about docstring contracts. See spec §14.1.

The functions here are stable. Internal data types (FunctionInfo,
ParsedDocstring) are accessible via this module but their shapes are
NOT stable API — they may change in any docpact release. Use the
assertion helpers, not the underlying types, in test code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def assert_tier(func: Callable[..., object], expected_tier: int) -> None:
    """Assert that a function is assigned to the expected tier.

    Args:
        func: The function to check.
        expected_tier: 1, 2, 3, or 4.

    Raises:
        AssertionError: The function is not in the expected tier.

    Stability: stable
    """
    raise NotImplementedError


def assert_section_present(func: Callable[..., object], section_name: str) -> None:
    """Assert that a docstring section is present (and non-empty in canonical form).

    Args:
        func: The function whose docstring is checked.
        section_name: e.g., "Constraints", "Stability", "MCP".

    Raises:
        AssertionError: The section is absent or empty without the
            canonical None. marker.

    Stability: stable
    """
    raise NotImplementedError


def assert_params_match_signature(func: Callable[..., object]) -> None:
    """Assert that the Args section parameters match the function signature.

    Args:
        func: The function to check.

    Raises:
        AssertionError: Args contains parameters absent from the
            signature, or the signature contains parameters absent
            from Args.

    Stability: stable
    """
    raise NotImplementedError


def assert_mcp_schema_from_docstring(
    func: Callable[..., object],
) -> dict[str, object]:
    """Return the MCP schema docpact derives from the function's docstring.

    Does NOT import FastMCP. Does NOT generate or validate against a
    running schema. Validates that the docstring contains the information
    FastMCP needs.

    Args:
        func: The function whose docstring is parsed.

    Returns:
        A dict with shape {"description": str, "parameters": dict[str, dict]}.
        Use the result in further assertions for project-specific checks.

    Raises:
        AssertionError: The docstring is malformed or missing required
            sections for a Tier 3 function.

    Stability: stable
    """
    raise NotImplementedError


def get_parsed_docstring(func: Callable[..., object]) -> object:
    """Return the ParsedDocstring for a function.

    The return type is intentionally typed as `object` here because the
    internal ParsedDocstring shape is not stable API. Use it for ad-hoc
    inspection; prefer the assert_* functions for stable test surface.

    Args:
        func: The function whose docstring is parsed.

    Returns:
        ParsedDocstring (internal type).

    Stability: beta
    """
    raise NotImplementedError

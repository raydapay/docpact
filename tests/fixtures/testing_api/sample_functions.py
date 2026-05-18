"""Fixture functions for tests/test_testing.py.

These are intentionally simple; their docstrings exercise the
testing API surface rather than the full rule engine.
"""

from __future__ import annotations


def tier1_internal(x: int) -> int:
    """Return x doubled."""
    return x * 2


def tier2_public(name: str, count: int = 1) -> str:
    """Format a greeting.

    Args:
        name: Recipient name.
        count: Number of greetings.

    Returns:
        Formatted greeting string.
    """
    return f"Hello {name}! " * count


def no_docstring(x: int) -> int:
    return x


def no_args_section(x: int, y: int) -> int:
    """Add two numbers."""
    return x + y


def phantom_param_in_args(x: int) -> int:
    """Return x.

    Args:
        x: The input.
        ghost: Does not exist in signature.
    """
    return x


def missing_param_in_args(x: int, y: int) -> int:
    """Add two numbers.

    Args:
        x: First operand.
    """
    return x + y


def has_mcp_section(query: str, limit: int = 10) -> list[str]:
    """Search the collection.

    Args:
        query: Search query string.
        limit: Maximum number of results.

    Returns:
        List of matching document IDs.

    MCP:
        Searches indexed documents and returns matching IDs.
    """
    return []


def summary_only_mcp(query: str) -> list[str]:
    """Search indexed documents and return matching IDs.

    Args:
        query: Search query string.

    Returns:
        List of matching document IDs.
    """
    return []


def with_constraints(value: str) -> None:
    """Process a value.

    Args:
        value: The input value.

    Constraints:
        Value must be non-empty.
    """


def no_docstring_mcp(query: str) -> list[str]:
    return []

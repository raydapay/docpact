"""Tests for docpact.testing programmatic assertions API."""

from __future__ import annotations

import pytest

from docpact.testing import (
    assert_mcp_schema_from_docstring,
    assert_params_match_signature,
    assert_section_present,
    assert_tier,
    get_parsed_docstring,
)

# ---------------------------------------------------------------------------
# Fixture functions — defined inline so they are importable as live callables
# without adding tests/ to sys.path or creating package __init__ files.
# These are intentionally simple; their docstrings exercise the testing API.
# ---------------------------------------------------------------------------


def _fix_internal(x: int) -> int:
    """Return x doubled."""
    return x * 2


def fix_public(name: str, count: int = 1) -> str:
    """Format a greeting.

    Args:
        name: Recipient name.
        count: Number of greetings.

    Returns:
        Formatted greeting string.
    """
    return f"Hello {name}! " * count


def _fix_no_docstring(x: int) -> int:
    return x


def fix_no_args_section(x: int, y: int) -> int:
    """Add two numbers."""
    return x + y


def fix_phantom_param(x: int) -> int:
    """Return x.

    Args:
        x: The input.
        ghost: Does not exist in signature.
    """
    return x


def fix_missing_param(x: int, y: int) -> int:
    """Add two numbers.

    Args:
        x: First operand.
    """
    return x + y


def fix_has_mcp_section(query: str, limit: int = 10) -> list[str]:
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


def fix_summary_only_mcp(query: str) -> list[str]:
    """Search indexed documents and return matching IDs.

    Args:
        query: Search query string.

    Returns:
        List of matching document IDs.
    """
    return []


def fix_with_constraints(value: str) -> None:
    """Process a value.

    Args:
        value: The input value.

    Constraints:
        Value must be non-empty.
    """


def _fix_no_docstring_mcp(query: str) -> list[str]:
    return []


# ---------------------------------------------------------------------------
# assert_tier
# ---------------------------------------------------------------------------


def test_assert_tier_tier1_passes() -> None:
    assert_tier(_fix_internal, 1)


def test_assert_tier_tier2_passes() -> None:
    assert_tier(fix_public, 2)


def test_assert_tier_wrong_tier_raises() -> None:
    with pytest.raises(AssertionError, match="Tier"):
        assert_tier(_fix_internal, 3)


def test_assert_tier_message_contains_actual_and_expected() -> None:
    with pytest.raises(AssertionError) as exc_info:
        assert_tier(_fix_internal, 3)
    msg = str(exc_info.value)
    assert "1" in msg  # actual tier
    assert "3" in msg  # expected tier


# ---------------------------------------------------------------------------
# assert_section_present
# ---------------------------------------------------------------------------


def test_section_present_passes_when_section_exists() -> None:
    assert_section_present(fix_with_constraints, "Constraints")


def test_section_present_raises_when_missing() -> None:
    with pytest.raises(AssertionError, match="missing section"):
        assert_section_present(_fix_internal, "Constraints")


def test_section_present_raises_when_no_docstring() -> None:
    with pytest.raises(AssertionError, match="no docstring"):
        assert_section_present(_fix_no_docstring, "Args")


def test_section_present_raises_for_absent_section() -> None:
    with pytest.raises(AssertionError, match="Stability"):
        assert_section_present(fix_public, "Stability")


def test_section_present_args_passes() -> None:
    assert_section_present(fix_public, "Args")


def test_section_present_returns_passes() -> None:
    assert_section_present(fix_public, "Returns")


# ---------------------------------------------------------------------------
# assert_params_match_signature
# ---------------------------------------------------------------------------


def test_params_match_passes_when_consistent() -> None:
    assert_params_match_signature(fix_public)


def test_params_match_passes_when_no_docstring() -> None:
    assert_params_match_signature(_fix_no_docstring)


def test_params_match_passes_when_no_args_section() -> None:
    assert_params_match_signature(fix_no_args_section)


def test_params_match_raises_on_phantom_param() -> None:
    with pytest.raises(AssertionError, match="ghost"):
        assert_params_match_signature(fix_phantom_param)


def test_params_match_raises_on_missing_param() -> None:
    with pytest.raises(AssertionError, match="y"):
        assert_params_match_signature(fix_missing_param)


def test_params_match_message_includes_absent_from_signature() -> None:
    with pytest.raises(AssertionError) as exc_info:
        assert_params_match_signature(fix_phantom_param)
    msg = str(exc_info.value)
    assert "ghost" in msg
    assert "absent from signature" in msg


def test_params_match_message_includes_absent_from_args() -> None:
    with pytest.raises(AssertionError) as exc_info:
        assert_params_match_signature(fix_missing_param)
    msg = str(exc_info.value)
    assert "y" in msg
    assert "absent from Args" in msg


# ---------------------------------------------------------------------------
# assert_mcp_schema_from_docstring
# ---------------------------------------------------------------------------


def test_mcp_schema_returns_description_and_parameters() -> None:
    schema = assert_mcp_schema_from_docstring(fix_has_mcp_section)
    assert "description" in schema
    assert "parameters" in schema


def test_mcp_schema_uses_mcp_section_body() -> None:
    schema = assert_mcp_schema_from_docstring(fix_has_mcp_section)
    assert isinstance(schema["description"], str)
    assert "Searches indexed documents" in schema["description"]


def test_mcp_schema_falls_back_to_summary() -> None:
    schema = assert_mcp_schema_from_docstring(fix_summary_only_mcp)
    assert "Search indexed documents" in schema["description"]


def test_mcp_schema_parameters_keys_match_args() -> None:
    schema = assert_mcp_schema_from_docstring(fix_has_mcp_section)
    params = schema["parameters"]
    assert isinstance(params, dict)
    assert set(params) == {"query", "limit"}


def test_mcp_schema_parameters_values_are_strings() -> None:
    schema = assert_mcp_schema_from_docstring(fix_has_mcp_section)
    for v in schema["parameters"].values():  # type: ignore[union-attr]
        assert isinstance(v, str)


def test_mcp_schema_raises_when_no_docstring() -> None:
    with pytest.raises(AssertionError, match="no docstring"):
        assert_mcp_schema_from_docstring(_fix_no_docstring_mcp)


# ---------------------------------------------------------------------------
# get_parsed_docstring
# ---------------------------------------------------------------------------


def test_get_parsed_docstring_returns_none_when_no_docstring() -> None:
    result = get_parsed_docstring(_fix_no_docstring)
    assert result is None


def test_get_parsed_docstring_returns_object_with_summary() -> None:
    result = get_parsed_docstring(fix_public)
    assert result is not None
    assert hasattr(result, "summary")
    assert "greeting" in result.summary.lower()  # type: ignore[union-attr]


def test_get_parsed_docstring_sections_accessible() -> None:
    result = get_parsed_docstring(fix_public)
    assert result is not None
    assert hasattr(result, "sections")
    assert "Args" in result.sections  # type: ignore[union-attr]


def test_get_parsed_docstring_with_constraints() -> None:
    result = get_parsed_docstring(fix_with_constraints)
    assert result is not None
    assert "Constraints" in result.sections  # type: ignore[union-attr]

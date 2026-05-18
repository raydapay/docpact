"""Public testing API — for use in project test suites.

This module is the v0.1 public surface for programmatic assertions
about docstring contracts. See spec §14.1.

The functions here are stable. Internal data types (FunctionInfo,
ParsedDocstring) are accessible via this module but their shapes are
NOT stable API — they may change in any docpact release. Use the
assertion helpers, not the underlying types, in test code.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import TYPE_CHECKING

from docpact.config import load_config
from docpact.parser.docstring import GoogleParser
from docpact.parser.source import extract_functions
from docpact.tiers import assign_tier

if TYPE_CHECKING:
    from collections.abc import Callable

    from docpact.model.function_info import FunctionInfo


def _qualname(func: Callable[..., object]) -> str:
    """Return a human-readable name for a callable."""
    return getattr(func, "__qualname__", repr(func))


def _resolve(func: Callable[..., object]) -> Callable[..., object]:
    """Follow __wrapped__ chains to reach the original function."""
    try:
        return inspect.unwrap(func)
    except Exception:
        return func


def _locate(func: Callable[..., object]) -> FunctionInfo:
    """Find the FunctionInfo for a live callable.

    Uses __code__.co_filename and co_firstlineno to pinpoint the
    definition without importing the analyzed module.
    """
    unwrapped = _resolve(func)
    code = getattr(unwrapped, "__code__", None)
    if code is None:
        raise AssertionError(
            f"{func!r} has no __code__ attribute — "
            "built-in functions and C extensions cannot be analysed by docpact."
        )

    source_file = Path(code.co_filename)
    first_line = code.co_firstlineno

    all_funcs = extract_functions(source_file)
    # Primary match: line number of the `def` statement.
    matches = [f for f in all_funcs if f.line == first_line]
    if not matches:
        raise AssertionError(
            f"docpact could not locate {_qualname(func)!r} at "
            f"{source_file}:{first_line}. "
            "The source file may be out of date with the running code."
        )
    if len(matches) == 1:
        return matches[0]

    # Disambiguate by bare name from __qualname__ (e.g. "Cls.method" → "method").
    bare_name = _qualname(unwrapped).split(".")[-1]
    named = [f for f in matches if f.name == bare_name]
    if named:
        return named[0]
    return matches[0]


def assert_tier(func: Callable[..., object], expected_tier: int) -> None:
    """Assert that a function is assigned to the expected tier.

    Args:
        func: The function to check.
        expected_tier: 1, 2, 3, or 4.

    Raises:
        AssertionError: The function is not in the expected tier.

    Stability: stable
    """
    info = _locate(func)
    config = load_config(info.file_path.parent)
    actual = assign_tier(info, config.tier_overrides)
    if actual != expected_tier:
        raise AssertionError(
            f"{_qualname(func)!r} is Tier {actual}, expected Tier {expected_tier}."
        )


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
    info = _locate(func)
    if info.docstring_raw is None:
        raise AssertionError(
            f"{_qualname(func)!r} has no docstring — cannot check for section {section_name!r}."
        )

    doc = GoogleParser().parse(info.docstring_raw)
    section = doc.sections.get(section_name)
    if section is None:
        raise AssertionError(f"{_qualname(func)!r} docstring is missing section {section_name!r}.")

    # Body "None." satisfies the check (canonical explicit-empty form).
    body = (section.body or "").strip()
    if body == "None.":
        return

    # A section with entries is non-empty.
    if section.entries:
        return

    # Body present and non-empty (not "None.").
    if body:
        return

    raise AssertionError(
        f"{_qualname(func)!r} section {section_name!r} is present but empty. "
        "Use 'None.' as the body to document an intentionally empty section."
    )


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
    info = _locate(func)
    if info.docstring_raw is None:
        return  # No docstring — nothing to check.

    doc = GoogleParser().parse(info.docstring_raw)
    args_section = doc.sections.get("Args")
    if args_section is None:
        return  # No Args section — nothing to check.

    documented: set[str] = (
        {e.key.lstrip("*") for e in args_section.entries} if args_section.entries else set()
    )

    # Parameters valid to document (everything except the bound receiver).
    valid: set[str] = {p.name for p in info.parameters if p.kind != "bound"}
    # Parameters that must be documented (positional and keyword).
    required: set[str] = {p.name for p in info.parameters if p.kind in ("positional", "keyword")}

    issues: list[str] = []
    for name in sorted(documented - valid):
        issues.append(f"  - {name!r}: documented in Args but absent from signature")
    for name in sorted(required - documented):
        issues.append(f"  - {name!r}: present in signature but absent from Args")

    if issues:
        raise AssertionError(
            f"{_qualname(func)!r} Args section does not match signature:\n" + "\n".join(issues)
        )


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
        A dict with shape {"description": str, "parameters": dict[str, str]}.
        Use the result in further assertions for project-specific checks.

    Raises:
        AssertionError: The docstring is malformed or missing required
            sections for a Tier 3 function.

    Stability: stable
    """
    info = _locate(func)
    if info.docstring_raw is None:
        raise AssertionError(f"{_qualname(func)!r} has no docstring — cannot derive MCP schema.")

    doc = GoogleParser().parse(info.docstring_raw)

    # Description: prefer the MCP section body, fall back to summary.
    mcp_section = doc.sections.get("MCP")
    if mcp_section is not None and mcp_section.body:
        description = mcp_section.body.strip()
    else:
        description = doc.summary.strip()

    if not description:
        raise AssertionError(
            f"{_qualname(func)!r} docstring has no usable description "
            "(neither a non-empty MCP section nor a summary line)."
        )

    # Parameters: build name → description from Args entries.
    parameters: dict[str, str] = {}
    args_section = doc.sections.get("Args")
    if args_section and args_section.entries:
        for entry in args_section.entries:
            bare_name = entry.key.lstrip("*")
            parameters[bare_name] = entry.description

    return {"description": description, "parameters": parameters}


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
    info = _locate(func)
    if info.docstring_raw is None:
        return None
    return GoogleParser().parse(info.docstring_raw)

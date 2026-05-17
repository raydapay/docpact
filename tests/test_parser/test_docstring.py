"""Tests for docpact.parser.docstring — GoogleParser."""

from __future__ import annotations

from pathlib import Path

import pytest

from docpact.parser.docstring import GoogleParser


@pytest.fixture()
def parser() -> GoogleParser:
    return GoogleParser()


# ---------------------------------------------------------------------------
# Summary and description
# ---------------------------------------------------------------------------


def test_summary_only(parser: GoogleParser) -> None:
    doc = parser.parse("Do something.")
    assert doc.summary == "Do something."
    assert doc.description is None
    assert doc.sections == {}


def test_summary_extracted(parser: GoogleParser) -> None:
    raw = "Parse a filter expression.\n\nArgs:\n    x: The value.\n"
    doc = parser.parse(raw)
    assert doc.summary == "Parse a filter expression."


def test_extended_description(parser: GoogleParser) -> None:
    raw = (
        "Parse a filter expression.\n\n"
        "This is the extended description.\n"
        "It spans multiple lines.\n\n"
        "Args:\n    x: The value.\n"
    )
    doc = parser.parse(raw)
    assert doc.summary == "Parse a filter expression."
    assert doc.description is not None
    assert "extended description" in doc.description


def test_description_none_when_no_body(parser: GoogleParser) -> None:
    raw = "Parse a filter expression.\n\nArgs:\n    x: The value.\n"
    doc = parser.parse(raw)
    assert doc.description is None


def test_raw_preserved(parser: GoogleParser) -> None:
    raw = "  Summary.  \n"
    doc = parser.parse(raw)
    assert doc.raw == raw


# ---------------------------------------------------------------------------
# Args section
# ---------------------------------------------------------------------------


def test_args_section_single_entry(parser: GoogleParser) -> None:
    raw = "Summary.\n\nArgs:\n    x: The value.\n"
    doc = parser.parse(raw)
    assert "Args" in doc.sections
    entries = doc.sections["Args"].entries
    assert len(entries) == 1
    assert entries[0].key == "x"
    assert entries[0].description == "The value."


def test_args_section_multiple_entries(parser: GoogleParser) -> None:
    raw = (
        "Summary.\n\nArgs:\n"
        "    expression: The filter DSL expression.\n"
        "    strict: Whether to use strict mode.\n"
    )
    doc = parser.parse(raw)
    entries = doc.sections["Args"].entries
    assert len(entries) == 2
    assert entries[0].key == "expression"
    assert entries[1].key == "strict"


def test_args_multiline_description(parser: GoogleParser) -> None:
    raw = "Summary.\n\nArgs:\n    x: First line of description.\n        Continuation line.\n"
    doc = parser.parse(raw)
    entry = doc.sections["Args"].entries[0]
    assert "First line" in entry.description


def test_args_none_form_recovered(parser: GoogleParser) -> None:
    raw = "Summary.\n\nArgs:\n    None.\n"
    doc = parser.parse(raw)
    assert "Args" in doc.sections
    sec = doc.sections["Args"]
    assert sec.body == "None."
    assert sec.entries == ()


# ---------------------------------------------------------------------------
# Returns section
# ---------------------------------------------------------------------------


def test_returns_section(parser: GoogleParser) -> None:
    raw = "Summary.\n\nReturns:\n    The parsed result.\n"
    doc = parser.parse(raw)
    assert "Returns" in doc.sections
    assert doc.sections["Returns"].body is not None
    assert "parsed result" in doc.sections["Returns"].body


def test_returns_none_form_recovered(parser: GoogleParser) -> None:
    # griffe returns Returns: None. as a returns item with description "None."
    raw = "Summary.\n\nReturns:\n    None.\n"
    doc = parser.parse(raw)
    assert "Returns" in doc.sections
    assert doc.sections["Returns"].body is not None


# ---------------------------------------------------------------------------
# Raises section
# ---------------------------------------------------------------------------


def test_raises_section(parser: GoogleParser) -> None:
    raw = (
        "Summary.\n\nRaises:\n"
        "    ValueError: When the input is invalid.\n"
        "    TypeError: When the type is wrong.\n"
    )
    doc = parser.parse(raw)
    assert "Raises" in doc.sections
    entries = doc.sections["Raises"].entries
    assert len(entries) == 2
    assert entries[0].key == "ValueError"
    assert "invalid" in entries[0].description
    assert entries[1].key == "TypeError"


def test_raises_none_form_recovered(parser: GoogleParser) -> None:
    raw = "Summary.\n\nRaises:\n    None.\n"
    doc = parser.parse(raw)
    assert "Raises" in doc.sections
    sec = doc.sections["Raises"]
    assert sec.body == "None."
    assert sec.entries == ()


# ---------------------------------------------------------------------------
# Extended sections (admonitions)
# ---------------------------------------------------------------------------


def test_constraints_section(parser: GoogleParser) -> None:
    raw = (
        "Summary.\n\nConstraints:\n"
        "    Must hold a session lock.\n"
        "    Tested at up to 10K records.\n"
    )
    doc = parser.parse(raw)
    assert "Constraints" in doc.sections
    body = doc.sections["Constraints"].body
    assert body is not None
    assert "session lock" in body


def test_constraints_none_form(parser: GoogleParser) -> None:
    raw = "Summary.\n\nConstraints:\n    None beyond type annotations.\n"
    doc = parser.parse(raw)
    assert "Constraints" in doc.sections
    assert "None beyond type annotations" in (doc.sections["Constraints"].body or "")


def test_notes_section(parser: GoogleParser) -> None:
    raw = "Summary.\n\nNotes:\n    Uses a recursive descent parser.\n"
    doc = parser.parse(raw)
    assert "Notes" in doc.sections
    assert "recursive" in (doc.sections["Notes"].body or "")


def test_mcp_section(parser: GoogleParser) -> None:
    raw = "Summary.\n\nMCP:\n    Use this tool to search documents.\n"
    doc = parser.parse(raw)
    assert "MCP" in doc.sections
    assert "search" in (doc.sections["MCP"].body or "")


def test_mutates_section(parser: GoogleParser) -> None:
    raw = "Summary.\n\nMutates:\n    Appends to the audit log.\n"
    doc = parser.parse(raw)
    assert "Mutates" in doc.sections


def test_alternatives_section(parser: GoogleParser) -> None:
    raw = "Summary.\n\nAlternatives:\n    lark-parser was evaluated and rejected.\n"
    doc = parser.parse(raw)
    assert "Alternatives" in doc.sections


def test_see_also_section(parser: GoogleParser) -> None:
    raw = "Summary.\n\nSee Also:\n    module.func -- reason for reference\n"
    doc = parser.parse(raw)
    assert "See Also" in doc.sections
    assert "module.func" in (doc.sections["See Also"].body or "")


# ---------------------------------------------------------------------------
# Stability inline field
# ---------------------------------------------------------------------------


def test_stability_stable(parser: GoogleParser) -> None:
    raw = "Summary.\n\nStability: stable\n"
    doc = parser.parse(raw)
    assert "Stability" in doc.sections
    assert doc.sections["Stability"].body == "stable"


def test_stability_beta(parser: GoogleParser) -> None:
    raw = "Summary.\n\nStability: beta\n"
    doc = parser.parse(raw)
    assert doc.sections["Stability"].body == "beta"


def test_stability_between_sections(parser: GoogleParser) -> None:
    raw = "Summary.\n\nArgs:\n    x: A param.\n\nStability: stable\n\nNotes:\n    A note.\n"
    doc = parser.parse(raw)
    assert "Stability" in doc.sections
    assert doc.sections["Stability"].body == "stable"
    assert "Args" in doc.sections
    assert "Notes" in doc.sections


def test_stability_not_in_description(parser: GoogleParser) -> None:
    raw = "Summary.\n\nStability: stable\n"
    doc = parser.parse(raw)
    # The Stability line should not bleed into the description
    assert doc.description is None or "Stability" not in doc.description


# ---------------------------------------------------------------------------
# Examples section
# ---------------------------------------------------------------------------


def test_examples_section(parser: GoogleParser) -> None:
    raw = "Summary.\n\nExamples:\n    >>> result = do_thing()\n    True\n"
    doc = parser.parse(raw)
    assert "Examples" in doc.sections
    assert "do_thing" in (doc.sections["Examples"].body or "")


# ---------------------------------------------------------------------------
# Full Tier 3 docstring (spec §20.3)
# ---------------------------------------------------------------------------

_TIER3_DOC = """\
Search documents in a collection using full-text query.

Args:
    query: Search query string. Supports boolean operators.
    collection: Collection identifier as returned by list_collections.
    max_results: Maximum number of results to return.
    include_metadata: When True, include full metadata in results.

Returns:
    List of result objects ordered by relevance score descending.

Raises:
    CollectionNotFoundError: collection does not exist.
    QueryError: query cannot be parsed.

Constraints:
    Caller must hold a session with read permission on the collection.
    Backed by a search cluster; subject to cluster availability.

Mutates:
    Appends to the query statistics log (best-effort, non-blocking).

Stability: stable

MCP:
    Searches documents in a specified collection and returns ranked
    results. Use this tool when the user asks to find documents.

Examples:
    >>> results = search_documents("climate change", "papers")
    >>> len(results) <= 10
    True
"""


def test_tier3_summary(parser: GoogleParser) -> None:
    doc = parser.parse(_TIER3_DOC)
    assert doc.summary == "Search documents in a collection using full-text query."


def test_tier3_args_count(parser: GoogleParser) -> None:
    doc = parser.parse(_TIER3_DOC)
    assert len(doc.sections["Args"].entries) == 4


def test_tier3_args_names(parser: GoogleParser) -> None:
    doc = parser.parse(_TIER3_DOC)
    arg_names = [e.key for e in doc.sections["Args"].entries]
    assert arg_names == ["query", "collection", "max_results", "include_metadata"]


def test_tier3_raises_entries(parser: GoogleParser) -> None:
    doc = parser.parse(_TIER3_DOC)
    raise_keys = [e.key for e in doc.sections["Raises"].entries]
    assert "CollectionNotFoundError" in raise_keys
    assert "QueryError" in raise_keys


def test_tier3_constraints_present(parser: GoogleParser) -> None:
    doc = parser.parse(_TIER3_DOC)
    assert "Constraints" in doc.sections
    assert "session" in (doc.sections["Constraints"].body or "")


def test_tier3_stability(parser: GoogleParser) -> None:
    doc = parser.parse(_TIER3_DOC)
    assert doc.sections["Stability"].body == "stable"


def test_tier3_mcp_section(parser: GoogleParser) -> None:
    doc = parser.parse(_TIER3_DOC)
    assert "MCP" in doc.sections
    assert "ranked" in (doc.sections["MCP"].body or "")


def test_tier3_mutates_present(parser: GoogleParser) -> None:
    doc = parser.parse(_TIER3_DOC)
    assert "Mutates" in doc.sections


def test_tier3_examples_present(parser: GoogleParser) -> None:
    doc = parser.parse(_TIER3_DOC)
    assert "Examples" in doc.sections


def test_tier3_all_required_sections_present(parser: GoogleParser) -> None:
    doc = parser.parse(_TIER3_DOC)
    required = {"Args", "Returns", "Raises", "Constraints", "Stability", "MCP"}
    missing = required - set(doc.sections.keys())
    assert not missing, f"Missing sections: {missing}"


# ---------------------------------------------------------------------------
# format_name
# ---------------------------------------------------------------------------


def test_format_name(parser: GoogleParser) -> None:
    assert parser.format_name() == "google"


# ---------------------------------------------------------------------------
# Integration: parse from real fixture docstring
# ---------------------------------------------------------------------------


def test_integration_real_fixture() -> None:
    fixtures = Path(__file__).parent.parent / "fixtures"
    from docpact.parser.source import extract_functions

    fns = extract_functions(fixtures / "tier3" / "mcp_tool.py")
    search = next(f for f in fns if f.name == "search_documents")
    assert search.docstring_raw is not None
    p = GoogleParser()
    doc = p.parse(search.docstring_raw)
    assert doc.summary.startswith("Search documents")
    assert "Args" in doc.sections
    assert "Stability" in doc.sections
    assert "MCP" in doc.sections

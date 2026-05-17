"""Tier 3 fixture: MCP-exposed tools (spec §20.3 example and variants)."""

from __future__ import annotations

from typing import Annotated


class mcp:  # noqa: N801
    """Minimal stub so this fixture is importable without fastmcp."""

    @staticmethod
    def tool(*args: object, **kwargs: object) -> object:
        def decorator(fn: object) -> object:
            return fn

        return decorator if not args else args[0]

    @staticmethod
    def resource(*args: object, **kwargs: object) -> object:
        def decorator(fn: object) -> object:
            return fn

        return decorator if not args else args[0]


@mcp.tool()
def search_documents(
    query: str,
    collection: str,
    max_results: Annotated[int, "ge=1, le=100"] = 10,
    include_metadata: bool = False,
) -> list[dict[str, object]]:
    """Search documents in a collection using full-text query.

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
    raise NotImplementedError


@mcp.tool(description="Lists all available collections.")
def list_collections() -> list[str]:
    """List all collections available in the server.

    Returns:
        List of collection identifier strings.

    Raises:
        None.

    Constraints:
        None beyond type annotations.

    Stability: stable
    """
    raise NotImplementedError

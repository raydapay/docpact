"""Edge case fixture: various decorator forms."""

from __future__ import annotations


class mcp:  # noqa: N801
    @staticmethod
    def tool(*args: object, **kwargs: object) -> object:
        def d(fn: object) -> object:
            return fn

        return d if not args else args[0]


class app:  # noqa: N801
    @staticmethod
    def get(path: str) -> object:
        def d(fn: object) -> object:
            return fn

        return d


@mcp.tool()
def plain_call() -> None:
    """Plain decorator call with no arguments."""
    pass


@mcp.tool(description="A description string.")
def with_description() -> None:
    """Decorator with description= keyword argument."""
    pass


@app.get("/path")
def route_handler() -> None:
    """FastAPI-style route decorator."""
    pass


def no_decorator() -> None:
    """Function with no decorators."""
    pass


class _PrivateClass:
    @staticmethod
    def static_method() -> None:
        """Static method on a private class."""
        pass

    @classmethod
    def class_method(cls) -> None:
        """Class method on a private class."""
        pass

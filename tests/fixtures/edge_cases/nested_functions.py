"""Edge case fixture: nested functions and nested classes."""

from __future__ import annotations


def outer_function(x: int) -> int:
    """Outer function that contains a nested function.

    Args:
        x: Input value.

    Returns:
        Processed value.
    """

    def inner_helper(v: int) -> int:
        """Inner helper; not a method, so no bound parameter."""
        return v * 2

    return inner_helper(x)


class Container:
    """Class that contains a nested class."""

    def method(self) -> None:
        """Method that contains a nested function."""

        def local_fn(y: str) -> str:
            """Local function inside a method; not a method."""
            return y.upper()

        local_fn("test")

    class Inner:
        """Nested class — its methods ARE methods."""

        def inner_method(self) -> None:
            """Method on a nested class."""
            pass

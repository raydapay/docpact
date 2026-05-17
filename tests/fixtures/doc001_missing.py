"""Fixture for DOC001: functions missing docstrings at various tiers."""

from __future__ import annotations


def public_no_doc(x: int, y: str) -> bool:
    return bool(x)


def public_with_doc(x: int) -> str:
    """Return x as a string.

    Args:
        x: The integer to convert.

    Returns:
        String representation.
    """
    return str(x)


def _private_no_doc(x: int) -> None:
    pass


class MyClass:
    def method_no_doc(self, value: str) -> None:
        pass

    def method_with_doc(self, value: str) -> None:
        """Process the value.

        Args:
            value: Input string.
        """

    def no_return_no_doc(self) -> None:
        pass

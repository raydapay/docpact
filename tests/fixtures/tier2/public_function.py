"""Tier 2 fixture: public functions and class methods with full signatures."""

from __future__ import annotations

from typing import Annotated


def parse_expression(
    expression: Annotated[str, "max 4096 chars"],
    strict: bool = False,
) -> dict[str, object]:
    """Parse a filter expression string into an AST.

    Args:
        expression: Filter expression in the project DSL.
        strict: When True, reject deprecated syntax.

    Returns:
        Parsed AST as a dictionary.

    Raises:
        ValueError: Expression contains unrecoverable syntax.

    Constraints:
        Parser allocations are proportional to expression depth.

    Notes:
        Uses a recursive descent parser.
    """
    raise NotImplementedError


def no_args_function() -> None:
    """Do something with no arguments."""
    pass


def varargs_function(*args: int, **kwargs: str) -> None:
    """Accept variable positional and keyword arguments.

    Args:
        *args: Integer arguments to accumulate.
        **kwargs: String keyword arguments to record.
    """
    pass


class PublicService:
    """A service class with various method types."""

    def __init__(self, name: str, timeout: int = 30) -> None:
        """Initialize the service.

        Args:
            name: Service identifier.
            timeout: Connection timeout in seconds.
        """
        self.name = name
        self.timeout = timeout

    def process(self, item: str) -> str:
        """Process a single item.

        Args:
            item: The item to process.

        Returns:
            Processed item string.
        """
        return item

    @classmethod
    def from_config(cls, config: dict[str, object]) -> "PublicService":
        """Construct a service from a configuration dictionary.

        Args:
            config: Configuration mapping with 'name' and 'timeout' keys.

        Returns:
            Configured service instance.
        """
        return cls(str(config["name"]))

    @staticmethod
    def validate(value: str) -> bool:
        """Check whether a value is valid.

        Args:
            value: String to validate.

        Returns:
            True if valid, False otherwise.
        """
        return bool(value.strip())

    @property
    def display_name(self) -> str:
        """Human-readable service name.

        Returns:
            The service name with underscores replaced by spaces.
        """
        return self.name.replace("_", " ").title()

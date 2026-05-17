"""Tier 1 fixture: simple internal functions (summary-only docstrings)."""


def _normalize(value: str) -> str:
    """Normalize a string to lowercase stripped form."""
    return value.strip().lower()


def _compute(x: int, y: int) -> int:
    return x + y


class _InternalHelper:
    def process(self, data: list[str]) -> list[str]:
        """Process a list of strings."""
        return [_normalize(s) for s in data]

    def _private_method(self) -> None:
        pass

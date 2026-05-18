"""Rule registry.

Maps rule codes to implementing functions. Rules self-register via
decorator when their module is imported.

The registry is populated at startup. Adding a rule requires only
creating a new module under rules/<namespace>/ — no changes to this
file or to a central catalog.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from docpact.model.diagnostic import RuleResult, Severity
from docpact.model.function_info import FunctionInfo
from docpact.model.parsed_docstring import ParsedDocstring


@dataclass(frozen=True, slots=True)
class RuleConfig:
    """Per-rule configuration."""

    severity: Severity
    options: dict[str, object]  # rule-specific options from config


RuleFn = Callable[[FunctionInfo, ParsedDocstring | None, RuleConfig], list[RuleResult]]


@dataclass(frozen=True, slots=True)
class RuleMetadata:
    """Metadata for a registered rule."""

    code: str
    namespace: str  # "DOC", "MCP", "FIX", etc.
    summary: str  # one-line description
    default_severity: Severity
    fixable: bool
    unsafe_fixable: bool


_RULES: dict[str, tuple[RuleMetadata, RuleFn]] = {}


def register(metadata: RuleMetadata) -> Callable[[RuleFn], RuleFn]:
    """Decorator that registers a rule function under the given metadata.

    Args:
        metadata: Static metadata for the rule (code, severity, fixability, etc.).

    Returns:
        Decorator that registers and returns the decorated function unchanged.
    """

    def decorator(fn: RuleFn) -> RuleFn:
        """Register fn under metadata.code and return fn unchanged.

        Args:
            fn: The rule function to register.

        Returns:
            The same function, unmodified.
        """
        if metadata.code in _RULES:
            raise ValueError(f"Rule {metadata.code} is already registered")
        _RULES[metadata.code] = (metadata, fn)
        return fn

    return decorator


def all_rules() -> dict[str, tuple[RuleMetadata, RuleFn]]:
    """Return a snapshot of all registered rules keyed by rule code.

    Returns:
        Dict mapping code string to (RuleMetadata, RuleFn) pairs.
    """
    return dict(_RULES)

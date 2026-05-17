"""Configuration loading.

Resolves configuration from pyproject.toml or docpact.toml per spec §14.
Returns a fully-resolved Config object with all defaults applied.

When both pyproject.toml [tool.docpact] and docpact.toml are present,
docpact.toml wins and a warning is emitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from docpact.model.diagnostic import Severity

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class Config:
    """Resolved configuration.

    Constructed by load_config. All fields are fully resolved; defaults
    are applied at construction time so consumers do not need to handle
    None.
    """

    schema: str = "1"
    docstring_format: str = "google"
    select: tuple[str, ...] = ("DOC", "MCP")
    ignore: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    heuristics_default: Severity = Severity.WARNING
    per_file_ignores: dict[str, tuple[str, ...]] = field(default_factory=dict)
    tier_overrides: dict[str, int] = field(default_factory=dict)
    rule_severities: dict[str, Severity] = field(default_factory=dict)


def load_config(start_path: Path) -> Config:
    """Load configuration starting from a given path.

    Walks upward from start_path looking for docpact.toml, then for
    pyproject.toml with a [tool.docpact] section. Returns a Config with
    defaults applied if neither is found.

    Args:
        start_path: Directory to begin the upward walk.

    Returns:
        Fully-resolved Config.

    Raises:
        ConfigError: A configuration file was found but could not be
            parsed, or contained invalid values.

    Constraints:
        Walks up to the filesystem root. Stops at the first config file
        found. Does not merge configs from multiple ancestor directories.

    Stability: beta
    """
    raise NotImplementedError("config loading not yet implemented")


class ConfigError(Exception):
    """Raised when configuration cannot be loaded or is invalid."""

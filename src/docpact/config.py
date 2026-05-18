"""Configuration loading.

Resolves configuration from pyproject.toml or docpact.toml per spec §15.
Returns a fully-resolved Config object with all defaults applied.

When both pyproject.toml [tool.docpact] and docpact.toml are present
in the same directory, docpact.toml wins and a warning is issued via
the stdlib warnings module.
"""

from __future__ import annotations

import fnmatch
import tomllib
import warnings
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
    suppress_comment: tuple[str, ...] = ("nodo",)


_SEVERITY_MAP: dict[str, Severity] = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "off": Severity.OFF,
}

_VALID_FORMATS = {"google", "numpy"}


def _parse_severity(value: object, key: str) -> Severity:
    """Parse a severity value from config, raising ConfigError on invalid input."""
    if not isinstance(value, str):
        raise ConfigError(f"{key}: expected a string, got {type(value).__name__}")
    if value not in _SEVERITY_MAP:
        raise ConfigError(
            f"{key}: invalid severity {value!r}; must be one of {list(_SEVERITY_MAP)}"
        )
    return _SEVERITY_MAP[value]


def _parse_string_list(value: object, key: str) -> tuple[str, ...]:
    """Parse a list-of-strings value from config, raising ConfigError on invalid input."""
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{key}: expected a list of strings")
    return tuple(str(v) for v in value)


def _parse_section(raw: dict[str, object]) -> Config:
    """Build a Config from a raw [tool.docpact] or docpact.toml mapping."""
    schema: str = "1"
    docstring_format: str = "google"
    select: tuple[str, ...] = ("DOC", "MCP")
    ignore: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    heuristics_default: Severity = Severity.WARNING
    rule_severities: dict[str, Severity] = {}
    per_file_ignores: dict[str, tuple[str, ...]] = {}
    tier_overrides: dict[str, int] = {}

    if "schema" in raw:
        v = raw["schema"]
        if not isinstance(v, str):
            raise ConfigError("schema: expected a string")
        schema = v

    if "format" in raw:
        v = raw["format"]
        if not isinstance(v, str) or v not in _VALID_FORMATS:
            raise ConfigError(f"format: must be one of {sorted(_VALID_FORMATS)}")
        docstring_format = v

    if "select" in raw:
        select = _parse_string_list(raw["select"], "select")

    if "ignore" in raw:
        ignore = _parse_string_list(raw["ignore"], "ignore")

    if "exclude" in raw:
        exclude = _parse_string_list(raw["exclude"], "exclude")

    if "heuristics" in raw:
        heuristics_default = _parse_severity(raw["heuristics"], "heuristics")

    if "rules" in raw:
        rules_raw = raw["rules"]
        if not isinstance(rules_raw, dict):
            raise ConfigError("rules: expected a table")
        for k, val in rules_raw.items():
            code = str(k)
            rule_severities[code] = _parse_severity(val, f"rules.{code}")

    if "per-file-ignores" in raw:
        pfi_raw = raw["per-file-ignores"]
        if not isinstance(pfi_raw, dict):
            raise ConfigError("per-file-ignores: expected a table")
        for k, codes in pfi_raw.items():
            pattern = str(k)
            per_file_ignores[pattern] = _parse_string_list(codes, f"per-file-ignores.{pattern!r}")

    for _tier_key in ("per-file-tier", "tiers"):
        if _tier_key not in raw:
            continue
        if _tier_key == "tiers":
            warnings.warn(
                "[tool.docpact.tiers] is deprecated; rename the table to "
                "[tool.docpact.per-file-tier].",
                DeprecationWarning,
                stacklevel=2,
            )
        tiers_raw = raw[_tier_key]
        if not isinstance(tiers_raw, dict):
            raise ConfigError(f"{_tier_key}: expected a table")
        for k, tier_val in tiers_raw.items():
            pattern = str(k)
            if not isinstance(tier_val, int) or tier_val not in (1, 2, 3, 4):
                raise ConfigError(f"{_tier_key}.{pattern!r}: tier must be an integer 1-4")
            tier_overrides[pattern] = tier_val
        break  # per-file-tier wins; don't also process tiers

    suppress_comment: tuple[str, ...] = ("nodo",)
    if "suppress_comment" in raw:
        suppress_comment = _parse_string_list(raw["suppress_comment"], "suppress_comment")
        if not suppress_comment:
            raise ConfigError("suppress_comment: must contain at least one marker string")

    return Config(
        schema=schema,
        docstring_format=docstring_format,
        select=select,
        ignore=ignore,
        exclude=exclude,
        heuristics_default=heuristics_default,
        rule_severities=rule_severities,
        per_file_ignores=per_file_ignores,
        tier_overrides=tier_overrides,
        suppress_comment=suppress_comment,
    )


def _load_toml(path: Path) -> dict[str, object]:
    """Read and decode a TOML file, raising ConfigError on parse failure."""
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)  # type: ignore[return-value]
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: TOML parse error: {exc}") from exc


def _get_docpact_section(raw: dict[str, object]) -> dict[str, object] | None:
    """Extract [tool.docpact] from a pyproject.toml mapping, or None."""
    tool = raw.get("tool")
    if not isinstance(tool, dict):
        return None
    docpact = tool.get("docpact")  # ty: ignore[invalid-argument-type]
    if not isinstance(docpact, dict):
        return None
    return docpact  # type: ignore[return-value]


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
    current = start_path if start_path.is_dir() else start_path.parent

    while True:
        docpact_toml = current / "docpact.toml"
        pyproject_toml = current / "pyproject.toml"

        found_docpact = docpact_toml.exists()
        docpact_section: dict[str, object] | None = None

        if pyproject_toml.exists():
            raw_pyproject = _load_toml(pyproject_toml)
            docpact_section = _get_docpact_section(raw_pyproject)

        if found_docpact and docpact_section is not None:
            warnings.warn(
                f"Both {docpact_toml} and {pyproject_toml} [tool.docpact] found; "
                "docpact.toml takes precedence.",
                stacklevel=2,
            )

        if found_docpact:
            raw = _load_toml(docpact_toml)
            return _parse_section(raw)

        if docpact_section is not None:
            return _parse_section(docpact_section)

        parent = current.parent
        if parent == current:
            break
        current = parent

    return Config()


def rule_is_enabled(
    code: str,
    namespace: str,
    select: tuple[str, ...],
    ignore: tuple[str, ...] | frozenset[str],
) -> bool:
    """Return True if a rule is active under the given select/ignore sets.

    Args:
        code: Full rule code, e.g. "DOC007".
        namespace: Rule namespace prefix, e.g. "DOC".
        select: Active rule selectors (codes or namespace prefixes).
        ignore: Suppressed rule selectors (codes or namespace prefixes).

    Returns:
        True when the rule should run.
    """
    for pattern in ignore:
        if code == pattern or namespace == pattern or code.startswith(pattern):
            return False
    for pattern in select:
        if code == pattern or namespace == pattern or code.startswith(pattern):
            return True
    return False


def file_ignores_for(
    file_path: Path,
    per_file_ignores: dict[str, tuple[str, ...]],
) -> frozenset[str]:
    """Return the set of suppressed rule selectors for a given file.

    Args:
        file_path: Absolute or relative path to check.
        per_file_ignores: Mapping of fnmatch patterns to suppressed codes.

    Returns:
        Frozenset of suppressed selectors applicable to this file.
    """
    path_str = str(file_path)
    result: set[str] = set()
    for pattern, codes in per_file_ignores.items():
        if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(path_str, f"*/{pattern}"):
            result.update(codes)
    return frozenset(result)


def rule_is_file_ignored(code: str, namespace: str, ignores: frozenset[str]) -> bool:
    """Return True if a rule is suppressed by per-file-ignores patterns.

    Unlike rule_is_enabled, this only checks the ignore side — it does
    not require the rule to appear in a select list.

    Args:
        code: Full rule code, e.g. "TY001".
        namespace: Rule namespace prefix, e.g. "TY".
        ignores: Per-file ignore patterns from file_ignores_for().

    Returns:
        True when the rule should be skipped for this file.
    """
    return any(code == p or namespace == p or code.startswith(p) for p in ignores)


def file_is_excluded(file_path: Path, exclude: tuple[str, ...]) -> bool:
    """Return True if a file matches any exclude pattern.

    Args:
        file_path: Path to test.
        exclude: fnmatch glob patterns. A pattern ending with '/' is treated
            as a directory prefix: "migrations/" matches any file whose path
            contains that directory component.

    Returns:
        True when the file should be skipped.
    """
    path_str = str(file_path)
    for pattern in exclude:
        # Trailing '/' means "directory and all contents".
        effective = pattern.rstrip("/") + "/**" if pattern.endswith("/") else pattern
        if fnmatch.fnmatch(path_str, effective) or fnmatch.fnmatch(path_str, f"*/{effective}"):
            return True
    return False


class ConfigError(Exception):
    """Raised when configuration cannot be loaded or is invalid."""

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
class ConfigResult:
    """Result of loading configuration, bundling the config and its root directory.

    The root is the directory containing the config file that was found, or
    the start directory passed to load_config when no config file exists.
    It is used to anchor per-file glob patterns to the project root.

    Stability: beta
    """

    config: Config
    root: Path


@dataclass(frozen=True, slots=True)
class RegistryConfig:
    """Configuration for tool-registry detection (REG namespace; ADR-005).

    Drives same-file cross-checking of programmatic tool-registration entries
    against the functions they name. ``assign_tier`` and ``no_tier_floor``
    govern only the Tier 3 floor; the REG rules themselves run regardless of
    those two (they are gated by REG namespace selection alone).

    Stability: beta
    """

    tool_definition_class: tuple[str, ...] = ("ToolDefinition",)
    name_field: str = "name"
    description_field: str = "description"
    parameters_field: str = "parameters"
    assign_tier: bool = True
    no_tier_floor: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Config:
    """Resolved configuration.

    Constructed by load_config. All fields are fully resolved; defaults
    are applied at construction time so consumers do not need to handle
    None.
    """

    schema: str = "1"
    docstring_format: str = "google"
    select: tuple[str, ...] = ("DOC", "MCP", "PARSE")
    ignore: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    heuristics_default: Severity = Severity.WARNING
    per_file_ignores: dict[str, tuple[str, ...]] = field(default_factory=dict)
    tier_overrides: dict[str, int] = field(default_factory=dict)
    rule_severities: dict[str, Severity] = field(default_factory=dict)
    suppress_comment: tuple[str, ...] = ("nodo",)
    allow_pragma: bool = False
    respect_gitignore: bool = True
    require_examples_min_tier: int | None = None
    registry: RegistryConfig = field(default_factory=RegistryConfig)
    jobs: int = 1  # parallel worker processes; 1 = serial (default), 0 = auto (all cores)


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
    select: tuple[str, ...] = ("DOC", "MCP", "PARSE")
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

    allow_pragma: bool = False
    if "allow_pragma" in raw:
        v = raw["allow_pragma"]
        if not isinstance(v, bool):
            raise ConfigError("allow_pragma: expected a boolean")
        allow_pragma = v

    respect_gitignore: bool = True
    if "respect_gitignore" in raw:
        v = raw["respect_gitignore"]
        if not isinstance(v, bool):
            raise ConfigError("respect_gitignore: expected a boolean")
        respect_gitignore = v

    require_examples_min_tier: int | None = None
    if "require_examples_min_tier" in raw:
        v = raw["require_examples_min_tier"]
        if not isinstance(v, int) or v not in (1, 2, 3, 4):
            raise ConfigError("require_examples_min_tier: must be an integer 1-4")
        require_examples_min_tier = v

    registry = _parse_registry(raw["registry"]) if "registry" in raw else RegistryConfig()

    jobs: int = 1
    if "jobs" in raw:
        v = raw["jobs"]
        # bool is an int subclass; reject it explicitly so jobs = true is an error.
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ConfigError("jobs: must be a non-negative integer (0 = auto, 1 = serial)")
        jobs = v

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
        allow_pragma=allow_pragma,
        respect_gitignore=respect_gitignore,
        require_examples_min_tier=require_examples_min_tier,
        registry=registry,
        jobs=jobs,
    )


def _parse_registry(raw: object) -> RegistryConfig:
    """Build a RegistryConfig from a raw [tool.docpact.registry] mapping."""
    if not isinstance(raw, dict):
        raise ConfigError("registry: expected a table")
    data: dict[str, object] = {str(k): v for k, v in raw.items()}

    defaults = RegistryConfig()
    tool_classes = defaults.tool_definition_class
    if "tool_definition_class" in data:
        tool_classes = _parse_string_list(
            data["tool_definition_class"], "registry.tool_definition_class"
        )

    def _field(key: str, default: str) -> str:
        """Return a required-string field's value, or its default if absent."""
        if key not in data:
            return default
        v = data[key]
        if not isinstance(v, str):
            raise ConfigError(f"registry.{key}: expected a string")
        return v

    assign_tier = defaults.assign_tier
    if "assign_tier" in data:
        v = data["assign_tier"]
        if not isinstance(v, bool):
            raise ConfigError("registry.assign_tier: expected a boolean")
        assign_tier = v

    no_tier_floor = defaults.no_tier_floor
    if "no_tier_floor" in data:
        no_tier_floor = _parse_string_list(data["no_tier_floor"], "registry.no_tier_floor")

    return RegistryConfig(
        tool_definition_class=tool_classes,
        name_field=_field("name_field", defaults.name_field),
        description_field=_field("description_field", defaults.description_field),
        parameters_field=_field("parameters_field", defaults.parameters_field),
        assign_tier=assign_tier,
        no_tier_floor=no_tier_floor,
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


def load_config(start_path: Path) -> ConfigResult:
    """Load configuration starting from a given path.

    Walks upward from start_path looking for docpact.toml, then for
    pyproject.toml with a [tool.docpact] section. Returns a ConfigResult
    with defaults applied if neither is found.

    Args:
        start_path: Directory (or file) to begin the upward walk.

    Returns:
        ConfigResult whose root is the directory containing the config file,
        or start_path (resolved to a directory) when no config is found.

    Raises:
        ConfigError: A configuration file was found but could not be
            parsed, or contained invalid values.

    Constraints:
        Walks up to the filesystem root. Stops at the first config file
        found. Does not merge configs from multiple ancestor directories.

    Stability: beta
    """
    initial_dir = start_path if start_path.is_dir() else start_path.parent
    current = initial_dir

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
            return ConfigResult(config=_parse_section(raw), root=current)

        if docpact_section is not None:
            return ConfigResult(config=_parse_section(docpact_section), root=current)

        parent = current.parent
        if parent == current:
            break
        current = parent

    return ConfigResult(config=Config(), root=initial_dir)


def load_config_from(path: Path) -> ConfigResult:
    """Load configuration from an explicit file path, bypassing discovery.

    Args:
        path: Path to a pyproject.toml or docpact.toml file.

    Returns:
        ConfigResult with root set to path.parent.

    Raises:
        ConfigError: The file could not be parsed or contained invalid values.

    Stability: beta
    """
    root = path.parent
    raw = _load_toml(path)
    if path.name == "pyproject.toml":
        section = _get_docpact_section(raw)
        config = _parse_section(section) if section is not None else Config()
    else:
        config = _parse_section(raw)
    return ConfigResult(config=config, root=root)


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
    root: Path,
) -> frozenset[str]:
    """Return the set of suppressed rule selectors for a given file.

    Args:
        file_path: Absolute or relative path to check.
        per_file_ignores: Mapping of fnmatch patterns to suppressed codes.
            Patterns are anchored to root (the project root directory).
        root: Project root directory; patterns are matched relative to it.

    Returns:
        Frozenset of suppressed selectors applicable to this file.
    """
    # as_posix() ensures forward slashes on Windows; str() would produce backslashes
    # which silently fail to match any user-written pattern.
    abs_str = file_path.as_posix()
    try:
        rel_str = file_path.relative_to(root).as_posix()
    except ValueError:
        rel_str = abs_str
    result: set[str] = set()
    for pattern, codes in per_file_ignores.items():
        if (
            fnmatch.fnmatch(rel_str, pattern)
            or fnmatch.fnmatch(abs_str, pattern)
            or fnmatch.fnmatch(abs_str, f"*/{pattern}")
        ):
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


def file_tier_override_for(
    file_path: Path,
    tier_overrides: dict[str, int],
    root: Path,
) -> int | None:
    """Return the tier override for a file, or None if no pattern matches.

    Args:
        file_path: Absolute or relative path to check.
        tier_overrides: Mapping of fnmatch patterns to tier numbers.
            Patterns are anchored to root (the project root directory).
        root: Project root directory; patterns are matched relative to it.

    Returns:
        The tier number of the first matching pattern, or None.
    """
    abs_str = file_path.as_posix()
    try:
        rel_str = file_path.relative_to(root).as_posix()
    except ValueError:
        rel_str = abs_str
    for pattern, tier in tier_overrides.items():
        if (
            fnmatch.fnmatch(rel_str, pattern)
            or fnmatch.fnmatch(abs_str, pattern)
            or fnmatch.fnmatch(abs_str, f"*/{pattern}")
        ):
            return tier
    return None


def file_matches_any(file_path: Path, patterns: tuple[str, ...], root: Path) -> bool:
    """Return True if a file matches any of the given root-anchored globs.

    Used for plain glob lists such as ``registry.no_tier_floor``. Unlike
    file_is_excluded, no trailing-slash directory shorthand is applied — the
    patterns are matched verbatim (relative-to-root, then absolute, then
    basename-anchored), the same three-way match used elsewhere.

    Args:
        file_path: Path to test.
        patterns: fnmatch glob patterns anchored to root.
        root: Project root directory; patterns are matched relative to it.

    Returns:
        True when the file matches at least one pattern.
    """
    abs_str = file_path.as_posix()
    try:
        rel_str = file_path.relative_to(root).as_posix()
    except ValueError:
        rel_str = abs_str
    for pattern in patterns:
        if (
            fnmatch.fnmatch(rel_str, pattern)
            or fnmatch.fnmatch(abs_str, pattern)
            or fnmatch.fnmatch(abs_str, f"*/{pattern}")
        ):
            return True
    return False


def file_is_excluded(file_path: Path, exclude: tuple[str, ...], root: Path) -> bool:
    """Return True if a file matches any exclude pattern.

    Args:
        file_path: Path to test.
        exclude: fnmatch glob patterns anchored to root. A pattern ending
            with '/' is treated as a directory prefix: "migrations/" matches
            any file whose path contains that directory component.
        root: Project root directory; patterns are matched relative to it.

    Returns:
        True when the file should be skipped.
    """
    abs_str = file_path.as_posix()
    try:
        rel_str = file_path.relative_to(root).as_posix()
    except ValueError:
        rel_str = abs_str
    for pattern in exclude:
        # Trailing '/' means "directory and all contents".
        effective = pattern.rstrip("/") + "/**" if pattern.endswith("/") else pattern
        if (
            fnmatch.fnmatch(rel_str, effective)
            or fnmatch.fnmatch(abs_str, effective)
            or fnmatch.fnmatch(abs_str, f"*/{effective}")
        ):
            return True
    return False


class ConfigError(Exception):
    """Raised when configuration cannot be loaded or is invalid."""

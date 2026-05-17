"""Tests for docpact.config — load_config, rule_is_enabled, helpers."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from docpact.config import (
    Config,
    ConfigError,
    file_ignores_for,
    file_is_excluded,
    load_config,
    rule_is_enabled,
)
from docpact.model.diagnostic import Severity

# ---------------------------------------------------------------------------
# Defaults when no config file is found
# ---------------------------------------------------------------------------


def test_load_config_returns_defaults_when_no_file(tmp_path: Path) -> None:
    empty = tmp_path / "project"
    empty.mkdir()
    cfg = load_config(empty)
    assert cfg.schema == "1"
    assert cfg.docstring_format == "google"
    assert "DOC" in cfg.select
    assert "MCP" in cfg.select
    assert cfg.ignore == ()
    assert cfg.exclude == ()
    assert cfg.tier_overrides == {}
    assert cfg.rule_severities == {}
    assert cfg.per_file_ignores == {}


def test_load_config_default_is_Config_instance(tmp_path: Path) -> None:
    cfg = load_config(tmp_path)
    assert isinstance(cfg, Config)


# ---------------------------------------------------------------------------
# pyproject.toml loading
# ---------------------------------------------------------------------------


def test_load_config_reads_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.docpact]\nschema = "1"\nselect = ["DOC"]\n')
    cfg = load_config(tmp_path)
    assert cfg.select == ("DOC",)


def test_load_config_ignores_pyproject_without_docpact_section(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n")
    cfg = load_config(tmp_path)
    assert cfg == Config()


def test_load_config_reads_full_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.docpact]\n"
        'schema = "1"\n'
        'format = "google"\n'
        'select = ["DOC", "MCP"]\n'
        'ignore = ["DOC013"]\n'
        'exclude = ["tests/"]\n'
        'heuristics = "warning"\n'
        "\n"
        "[tool.docpact.rules]\n"
        'DOC050 = "warning"\n'
        "\n"
        "[tool.docpact.per-file-ignores]\n"
        '"src/legacy/**" = ["DOC"]\n'
        "\n"
        "[tool.docpact.tiers]\n"
        '"src/routes.py" = 4\n'
    )
    cfg = load_config(tmp_path)
    assert cfg.schema == "1"
    assert cfg.ignore == ("DOC013",)
    assert cfg.exclude == ("tests/",)
    assert cfg.rule_severities == {"DOC050": Severity.WARNING}
    assert cfg.per_file_ignores == {"src/legacy/**": ("DOC",)}
    assert cfg.tier_overrides == {"src/routes.py": 4}


# ---------------------------------------------------------------------------
# docpact.toml loading
# ---------------------------------------------------------------------------


def test_load_config_reads_docpact_toml(tmp_path: Path) -> None:
    (tmp_path / "docpact.toml").write_text('select = ["DOC"]\nignore = ["DOC007"]\n')
    cfg = load_config(tmp_path)
    assert cfg.select == ("DOC",)
    assert cfg.ignore == ("DOC007",)


def test_docpact_toml_wins_over_pyproject(tmp_path: Path) -> None:
    (tmp_path / "docpact.toml").write_text('select = ["MCP"]\n')
    (tmp_path / "pyproject.toml").write_text('[tool.docpact]\nselect = ["DOC"]\n')
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cfg = load_config(tmp_path)

    assert cfg.select == ("MCP",)
    assert any("docpact.toml" in str(w.message) for w in caught)


# ---------------------------------------------------------------------------
# Upward walk
# ---------------------------------------------------------------------------


def test_load_config_walks_upward(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.docpact]\nschema = "2"\n')
    subdir = tmp_path / "src" / "pkg"
    subdir.mkdir(parents=True)
    cfg = load_config(subdir)
    assert cfg.schema == "2"


def test_load_config_stops_at_first_match(tmp_path: Path) -> None:
    # Inner config has schema=2, outer has schema=3.
    inner = tmp_path / "inner"
    inner.mkdir()
    (inner / "pyproject.toml").write_text('[tool.docpact]\nschema = "2"\n')
    (tmp_path / "pyproject.toml").write_text('[tool.docpact]\nschema = "3"\n')
    cfg = load_config(inner)
    assert cfg.schema == "2"


def test_load_config_accepts_file_path(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.docpact]\nschema = "1"\n')
    src_file = tmp_path / "main.py"
    src_file.write_text("def foo(): pass\n")
    cfg = load_config(src_file)
    assert cfg.schema == "1"


# ---------------------------------------------------------------------------
# ConfigError cases
# ---------------------------------------------------------------------------


def test_config_error_on_bad_toml(tmp_path: Path) -> None:
    (tmp_path / "docpact.toml").write_text("select = [not valid toml\n")
    with pytest.raises(ConfigError, match="TOML parse error"):
        load_config(tmp_path)


def test_config_error_on_bad_severity(tmp_path: Path) -> None:
    (tmp_path / "docpact.toml").write_text('[rules]\nDOC001 = "critical"\n')
    with pytest.raises(ConfigError, match="invalid severity"):
        load_config(tmp_path)


def test_config_error_on_invalid_tier(tmp_path: Path) -> None:
    (tmp_path / "docpact.toml").write_text('[tiers]\n"src/foo.py" = 5\n')
    with pytest.raises(ConfigError, match="tier must be"):
        load_config(tmp_path)


def test_config_error_on_bad_format(tmp_path: Path) -> None:
    (tmp_path / "docpact.toml").write_text('format = "sphinx"\n')
    with pytest.raises(ConfigError, match="format"):
        load_config(tmp_path)


def test_config_error_on_select_not_list(tmp_path: Path) -> None:
    (tmp_path / "docpact.toml").write_text('select = "DOC"\n')
    with pytest.raises(ConfigError, match="list of strings"):
        load_config(tmp_path)


# ---------------------------------------------------------------------------
# rule_is_enabled
# ---------------------------------------------------------------------------


def test_rule_enabled_by_namespace() -> None:
    assert rule_is_enabled("DOC007", "DOC", ("DOC",), ())


def test_rule_enabled_by_exact_code() -> None:
    assert rule_is_enabled("DOC007", "DOC", ("DOC007",), ())


def test_rule_disabled_by_exact_code_in_ignore() -> None:
    assert not rule_is_enabled("DOC007", "DOC", ("DOC",), ("DOC007",))


def test_rule_disabled_by_namespace_in_ignore() -> None:
    assert not rule_is_enabled("DOC007", "DOC", ("DOC", "MCP"), ("DOC",))


def test_rule_not_in_select_is_disabled() -> None:
    assert not rule_is_enabled("MCP001", "MCP", ("DOC",), ())


def test_rule_enabled_by_prefix() -> None:
    assert rule_is_enabled("DOC007", "DOC", ("DOC0",), ())


def test_ignore_takes_priority_over_select() -> None:
    assert not rule_is_enabled("DOC007", "DOC", ("DOC007",), ("DOC007",))


# ---------------------------------------------------------------------------
# file_ignores_for
# ---------------------------------------------------------------------------


def test_file_ignores_for_matches_pattern(tmp_path: Path) -> None:
    f = tmp_path / "src" / "legacy" / "old.py"
    pfi = {str(tmp_path / "src/legacy/**"): ("DOC",)}
    result = file_ignores_for(f, pfi)
    assert "DOC" in result


def test_file_ignores_for_no_match(tmp_path: Path) -> None:
    f = tmp_path / "src" / "new.py"
    pfi = {"src/legacy/**": ("DOC",)}
    result = file_ignores_for(f, pfi)
    assert result == frozenset()


def test_file_ignores_for_relative_pattern() -> None:
    f = Path("/project/tests/test_foo.py")
    pfi = {"tests/**": ("MCP001",)}
    result = file_ignores_for(f, pfi)
    assert "MCP001" in result


def test_file_ignores_for_multiple_patterns() -> None:
    f = Path("/project/src/legacy/old.py")
    pfi = {"src/legacy/**": ("DOC",), "src/**": ("MCP001",)}
    result = file_ignores_for(f, pfi)
    assert "DOC" in result
    assert "MCP001" in result


# ---------------------------------------------------------------------------
# file_is_excluded
# ---------------------------------------------------------------------------


def test_file_excluded_by_pattern() -> None:
    assert file_is_excluded(Path("/project/tests/test_foo.py"), ("tests/**",))


def test_file_not_excluded_when_no_match() -> None:
    assert not file_is_excluded(Path("/project/src/main.py"), ("tests/**",))


def test_file_excluded_by_glob(tmp_path: Path) -> None:
    f = tmp_path / "migrations" / "0001_initial.py"
    assert file_is_excluded(f, ("migrations/",))


def test_file_excluded_exact_match() -> None:
    assert file_is_excluded(
        Path("/project/src/_generated.py"),
        ("**/_generated.py",),
    )

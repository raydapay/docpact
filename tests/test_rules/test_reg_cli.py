"""End-to-end CLI tests for the REG namespace (extraction + rules + tier floor)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from docpact.cli import main

_TOOLS_SRC = '''"""Bot tools."""


def search_case(query: str) -> str:
    """Search for cases.

    Args:
        query: What to search for.

    Returns:
        Matches.
    """
    return query


BOT_TOOLS = [
    ToolDefinition(
        name="search_case",
        description="Search for cases.",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
    ),
]
'''


def _write(td: str, *, pyproject: str, source: str) -> Path:
    """Write a pyproject and bot_tools.py into the isolated dir; return its path."""
    td_path = Path(td)
    (td_path / "pyproject.toml").write_text(pyproject)
    (td_path / "bot_tools.py").write_text(source)
    return td_path


def test_reg001_fires_on_phantom_schema_param() -> None:
    src = _TOOLS_SRC.replace(
        '"properties": {"query": {"type": "string"}}',
        '"properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}',
    )
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        _write(td, pyproject='[tool.docpact]\nselect = ["REG"]\n', source=src)
        result = runner.invoke(main, ["check", "bot_tools.py"], catch_exceptions=False)
    assert "REG001" in result.output  # type: ignore[union-attr]
    assert "limit" in result.output  # type: ignore[union-attr]


def test_reg001_clean_when_schema_matches() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        _write(td, pyproject='[tool.docpact]\nselect = ["REG"]\n', source=_TOOLS_SRC)
        result = runner.invoke(main, ["check", "bot_tools.py"], catch_exceptions=False)
    assert "REG001" not in result.output  # type: ignore[union-attr]


def test_reg_not_run_when_namespace_not_selected() -> None:
    src = _TOOLS_SRC.replace(
        '"properties": {"query": {"type": "string"}}',
        '"properties": {"phantom": {"type": "string"}}',
    )
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        _write(td, pyproject='[tool.docpact]\nselect = ["DOC"]\n', source=src)
        result = runner.invoke(main, ["check", "bot_tools.py"], catch_exceptions=False)
    assert "REG001" not in result.output  # type: ignore[union-attr]


def test_reg002_off_by_default_even_when_selected() -> None:
    # search_register names a function not in the file → unmatched, but REG002 is OFF.
    src = _TOOLS_SRC.replace('name="search_case"', 'name="ghost_tool"')
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        _write(td, pyproject='[tool.docpact]\nselect = ["REG"]\n', source=src)
        result = runner.invoke(main, ["check", "bot_tools.py"], catch_exceptions=False)
    assert "REG002" not in result.output  # type: ignore[union-attr]


def test_reg002_opt_in_via_severity() -> None:
    src = _TOOLS_SRC.replace('name="search_case"', 'name="ghost_tool"')
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        pyproject = '[tool.docpact]\nselect = ["REG"]\n\n[tool.docpact.rules]\nREG002 = "warning"\n'
        _write(td, pyproject=pyproject, source=src)
        result = runner.invoke(main, ["check", "bot_tools.py"], catch_exceptions=False)
    assert "REG002" in result.output  # type: ignore[union-attr]
    assert "ghost_tool" in result.output  # type: ignore[union-attr]


def test_tier_floor_forces_tier3_sections() -> None:
    # A bare-summary tool function: at Tier 2 it would need only Args/Returns, but
    # the registry floor lifts it to Tier 3, so DOC012 demands Constraints etc.
    src = '''"""Bot tools."""


def search_case(query: str) -> str:
    """Search for cases.

    Args:
        query: What to search for.

    Returns:
        Matches.
    """
    return query


BOT_TOOLS = [
    {"name": "search_case", "parameters": {"properties": {"query": {}}}},
]
'''
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        _write(td, pyproject='[tool.docpact]\nselect = ["REG", "DOC012"]\n', source=src)
        result = runner.invoke(main, ["check", "bot_tools.py"], catch_exceptions=False)
    assert "DOC012" in result.output  # type: ignore[union-attr]


def test_no_tier_floor_glob_disables_bump() -> None:
    src = '''"""Bot tools."""


def search_case(query: str) -> str:
    """Search for cases.

    Args:
        query: What to search for.

    Returns:
        Matches.
    """
    return query


BOT_TOOLS = [
    {"name": "search_case", "parameters": {"properties": {"query": {}}}},
]
'''
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        _write(
            td,
            pyproject=(
                '[tool.docpact]\nselect = ["REG", "DOC012"]\n\n'
                "[tool.docpact.registry]\n"
                'no_tier_floor = ["bot_tools.py"]\n'
            ),
            source=src,
        )
        result = runner.invoke(main, ["check", "bot_tools.py"], catch_exceptions=False)
    # Tier stays 2 (Constraints not required) → DOC012 silent for the Tier-3-only sections.
    assert "DOC012" not in result.output  # type: ignore[union-attr]

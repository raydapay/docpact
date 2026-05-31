"""End-to-end CLI tests for the REG namespace (extraction + rules + tier floor)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from click.testing import CliRunner

from docpact.cli import _check_one_file, main
from docpact.config import Config, RegistryConfig

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


# --- call-based registration (ADR-011) + same-file REG010 (ADR-012) -----------

# The adopter shape: register_tool(ToolSpec(...)) with an indirect description, a
# same-file input_model, and a handler whose name differs from the tool name.
_CALL_BASED_SRC = '''"""Bot tools."""

from pydantic import BaseModel


class DescribeInput(BaseModel):
    """Input."""

    provider_id: str
    region: str


_DESC = """Describe a provider.

Args:
    provider_id: The provider id.
    region: The region.
"""


def describe_provider_tool(provider_id, region):
    """Describe a provider.

    Args:
        provider_id: The provider id.
        region: The region.

    Returns:
        A description.

    Raises:
        ValueError: On bad input.

    Constraints:
        Caller must hold view permission.

    Stability: beta

    MCP:
        Describe a provider by id and region.
    """


def _retag_iso(value):
    """Private helper."""


register_tool(ToolSpec(
    name="describe_provider",
    description=_DESC,
    input_model=DescribeInput,
    service_function=describe_provider_tool,
))
'''

_CALL_BASED_PYPROJECT = (
    '[tool.docpact]\nselect = ["REG", "DOC012"]\n\n'
    "[tool.docpact.registry]\n"
    'tool_definition_class = ["ToolSpec"]\n'
    'handler_field = "service_function"\n'
)


def test_call_based_floor_lands_on_handler_not_helpers() -> None:
    # The handler is floored to Tier 3 (its docstring is complete, so no DOC012),
    # while the private helper _retag_iso stays Tier 1 (also clean). The point:
    # the floor does not blanket the file — _retag_iso is never demanded Tier-3
    # sections. We assert the run is clean of DOC012 to prove no over-flooring.
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        _write(td, pyproject=_CALL_BASED_PYPROJECT, source=_CALL_BASED_SRC)
        result = runner.invoke(main, ["check", "bot_tools.py"], catch_exceptions=False)
    assert "DOC012" not in result.output  # type: ignore[union-attr]


def test_call_based_floor_demands_tier3_on_incomplete_handler() -> None:
    # Strip the handler's Tier-3 sections: now the floor must bite, demanding them.
    src = _CALL_BASED_SRC.replace(
        """    Returns:
        A description.

    Raises:
        ValueError: On bad input.

    Constraints:
        Caller must hold view permission.

    Stability: beta

    MCP:
        Describe a provider by id and region.
    """,
        "    Returns:\n        A description.\n    ",
    )
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        _write(td, pyproject=_CALL_BASED_PYPROJECT, source=src)
        result = runner.invoke(main, ["check", "bot_tools.py"], catch_exceptions=False)
    out = result.output  # type: ignore[union-attr]
    assert "DOC012" in out
    assert "Constraints" in out
    # The private helper is never floored, so it is not named in any DOC012 line.
    assert "_retag_iso" not in out


def test_same_file_reg010_fires_offline() -> None:
    # Args document a 'flags' param the model lacks, and omit the model's 'region'
    # — REG010 catches both with no --crossfile and no language server.
    src = _CALL_BASED_SRC.replace(
        "    provider_id: The provider id.\n    region: The region.",
        "    provider_id: The provider id.\n    flags: A nonexistent field.",
    )
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        _write(td, pyproject=_CALL_BASED_PYPROJECT, source=src)
        result = runner.invoke(main, ["check", "bot_tools.py"], catch_exceptions=False)
    out = result.output  # type: ignore[union-attr]
    assert "REG010" in out
    assert "region" in out  # model field missing from Args
    assert "flags" in out  # Args entry with no model field


def test_same_file_reg010_clean_when_parity_holds() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        _write(td, pyproject=_CALL_BASED_PYPROJECT, source=_CALL_BASED_SRC)
        result = runner.invoke(main, ["check", "bot_tools.py"], catch_exceptions=False)
    assert "REG010" not in result.output  # type: ignore[union-attr]


def test_same_file_reg010_respects_off_switch() -> None:
    src = _CALL_BASED_SRC.replace(
        "    provider_id: The provider id.\n    region: The region.",
        "    provider_id: The provider id.\n    flags: A nonexistent field.",
    )
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        _write(
            td,
            pyproject=_CALL_BASED_PYPROJECT + '\n[tool.docpact.rules]\nREG010 = "off"\n',
            source=src,
        )
        result = runner.invoke(main, ["check", "bot_tools.py"], catch_exceptions=False)
    assert "REG010" not in result.output  # type: ignore[union-attr]


def test_same_file_reg010_skipped_when_crossfile_active(tmp_path: Path) -> None:
    # Under --crossfile the cross-file pass owns REG010 for every model; the
    # same-file leg must not also fire (no double-report). Exercise the guard
    # directly via _check_one_file (no LSP server needed).
    src = _CALL_BASED_SRC.replace(
        "    provider_id: The provider id.\n    region: The region.",
        "    provider_id: The provider id.\n    flags: A nonexistent field.",
    )
    path = tmp_path / "bot_tools.py"
    path.write_text(src)
    config = dataclasses.replace(
        Config(),
        select=("REG",),
        registry=RegistryConfig(
            tool_definition_class=("ToolSpec",), handler_field="service_function"
        ),
    )

    offline, _ = _check_one_file(path, config, tmp_path, crossfile_active=False)
    assert any(r.code == "REG010" for r in offline)

    under_crossfile, _ = _check_one_file(path, config, tmp_path, crossfile_active=True)
    assert not any(r.code == "REG010" for r in under_crossfile)


def test_same_file_reg010_skips_imported_model() -> None:
    # input_model names a symbol with no same-file class def → no same-file leg
    # fires (an imported model is the cross-file pass's job). No REG010 offline.
    src = _CALL_BASED_SRC.replace("class DescribeInput(BaseModel):", "class _Unused(BaseModel):")
    src = src.replace("    provider_id: str\n    region: str", "    other: str")
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        _write(td, pyproject=_CALL_BASED_PYPROJECT, source=src)
        result = runner.invoke(main, ["check", "bot_tools.py"], catch_exceptions=False)
    assert "REG010" not in result.output  # type: ignore[union-attr]

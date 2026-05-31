"""Tests for the opt-in cross-file pass (REG010; ADR-009).

No real language server: resolution is driven against the fake server
subprocess (``tests/fixtures/fake_lsp_server.py``), pointed at real fixture
files written under tmp_path. The pure comparison (parity_findings), model
field extraction, and URI handling are unit-tested directly; the resolver and
the ``check --crossfile`` CLI path are tested end-to-end through the fake.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

from click.testing import CliRunner

from docpact.cli import main
from docpact.config import Config, LspConfig
from docpact.crossfile.resolver import _uri_to_path, check_input_model_parity
from docpact.model.diagnostic import Severity
from docpact.model.tool_registry import ModelRef, ToolRegistryEntry
from docpact.parser.pydantic_model import model_field_names
from docpact.rules.reg.reg010_input_model_parity import parity_findings

_FAKE = Path(__file__).parent / "fixtures" / "fake_lsp_server.py"

_SCHEMAS = (
    "from pydantic import BaseModel\n\n\n"
    "class SearchInput(BaseModel):\n"
    "    query: str\n"
    "    limit: int\n"
)


def _tools_src(description: str) -> str:
    """A tools.py registering 'search' with input_model=SearchInput."""
    return (
        "from schemas import SearchInput\n\n\n"
        "class ToolDefinition:\n"
        "    def __init__(self, **kw):\n"
        "        pass\n\n\n"
        "TOOLS = [\n"
        "    ToolDefinition(\n"
        '        name="search",\n'
        "        input_model=SearchInput,\n"
        f"        description={description!r},\n"
        "    ),\n"
        "]\n"
    )


def _entry(*, doc_keys: frozenset[str] | None, model: str = "SearchInput") -> ToolRegistryEntry:
    """A registry entry with the given documented Args keys and a model ref."""
    return ToolRegistryEntry(
        name="search",
        line=8,
        column=4,
        property_keys=None,
        has_description=True,
        input_model_ref=ModelRef(name=model, line=8, column=40),
        description_arg_keys=doc_keys,
    )


# --- parity_findings (pure) ---------------------------------------------------


def test_parity_match_yields_nothing() -> None:
    entry = _entry(doc_keys=frozenset({"query", "limit"}))
    assert (
        parity_findings(entry, Path("t.py"), frozenset({"query", "limit"}), Severity.WARNING) == []
    )


def test_parity_field_missing_in_doc() -> None:
    entry = _entry(doc_keys=frozenset({"query"}))
    results = parity_findings(entry, Path("t.py"), frozenset({"query", "limit"}), Severity.WARNING)
    assert len(results) == 1
    assert results[0].code == "REG010"
    assert "limit" in results[0].message and "not documented" in results[0].message


def test_parity_key_missing_in_model() -> None:
    entry = _entry(doc_keys=frozenset({"query", "bogus"}))
    results = parity_findings(entry, Path("t.py"), frozenset({"query"}), Severity.WARNING)
    assert len(results) == 1
    assert "bogus" in results[0].message and "no matching field" in results[0].message


def test_parity_reports_both_directions_sorted() -> None:
    entry = _entry(doc_keys=frozenset({"query", "extra"}))
    results = parity_findings(entry, Path("t.py"), frozenset({"query", "limit"}), Severity.WARNING)
    # 'limit' missing in doc, then 'extra' missing in model.
    assert [("limit" in r.message, "extra" in r.message) for r in results] == [
        (True, False),
        (False, True),
    ]
    assert all(r.location.line == 8 and r.location.column == 4 for r in results)


def test_parity_uses_configured_severity() -> None:
    entry = _entry(doc_keys=frozenset())
    results = parity_findings(entry, Path("t.py"), frozenset({"query"}), Severity.ERROR)
    assert results[0].severity == Severity.ERROR


# --- model_field_names --------------------------------------------------------


def test_model_field_names_basic() -> None:
    assert model_field_names(_SCHEMAS, "SearchInput") == frozenset({"query", "limit"})


def test_model_field_names_excludes_classvar_and_private() -> None:
    src = (
        "from pydantic import BaseModel\n"
        "from typing import ClassVar\n\n"
        "class M(BaseModel):\n"
        "    a: int\n"
        "    _b: int\n"
        "    c: ClassVar[int]\n"
    )
    assert model_field_names(src, "M") == frozenset({"a"})


def test_model_field_names_not_pydantic_is_none() -> None:
    assert model_field_names("class Plain:\n    a: int\n", "Plain") is None


def test_model_field_names_missing_class_is_none() -> None:
    assert model_field_names(_SCHEMAS, "Nonexistent") is None


def test_model_field_names_parse_error_is_none() -> None:
    assert model_field_names("class Broken(:\n", "Broken") is None


# --- _uri_to_path -------------------------------------------------------------


def test_uri_to_path_file_scheme(tmp_path: Path) -> None:
    target = tmp_path / "schemas.py"
    target.write_text("x = 1\n")
    assert _uri_to_path(target.as_uri()) == target


def test_uri_to_path_non_file_scheme_is_none() -> None:
    assert _uri_to_path("http://example.com/x.py") is None


# --- resolver against the fake server -----------------------------------------


def _config(workspace: Path, mode: str, target_uri: str) -> Config:
    """A REG-enabled Config whose LSP server is the fake in the given mode."""
    return dataclasses.replace(
        Config(),
        select=("REG",),
        lsp=LspConfig(server=(sys.executable, str(_FAKE), mode, target_uri), timeout=5.0),
    )


def _workspace(tmp_path: Path, description: str, schemas: str = _SCHEMAS) -> tuple[Path, Path]:
    """Write schemas.py + tools.py; return (tools_path, schemas_path)."""
    (tmp_path / "schemas.py").write_text(schemas)
    tools = tmp_path / "tools.py"
    tools.write_text(_tools_src(description))
    return tools, tmp_path / "schemas.py"


def test_resolver_match_no_findings(tmp_path: Path) -> None:
    tools, schemas = _workspace(tmp_path, "Search.\n\nArgs:\n    query: q\n    limit: l\n")
    config = _config(tmp_path, "location", schemas.as_uri())
    results = check_input_model_parity([tools], config, tmp_path, Severity.WARNING)
    assert results == []


def test_resolver_reports_drift(tmp_path: Path) -> None:
    # Doc documents only 'query'; the model also has 'limit'.
    tools, schemas = _workspace(tmp_path, "Search.\n\nArgs:\n    query: q\n")
    config = _config(tmp_path, "location", schemas.as_uri())
    results = check_input_model_parity([tools], config, tmp_path, Severity.WARNING)
    assert len(results) == 1
    assert results[0].code == "REG010"
    assert "limit" in results[0].message


def test_resolver_unresolved_is_skipped(tmp_path: Path) -> None:
    tools, schemas = _workspace(tmp_path, "Search.\n\nArgs:\n    query: q\n")
    config = _config(tmp_path, "empty", schemas.as_uri())
    config = dataclasses.replace(config, lsp=LspConfig(server=config.lsp.server, timeout=0.3))
    assert check_input_model_parity([tools], config, tmp_path, Severity.WARNING) == []


def test_resolver_non_pydantic_target_is_skipped(tmp_path: Path) -> None:
    plain = "class SearchInput:\n    query: str\n"
    tools, schemas = _workspace(tmp_path, "Search.\n\nArgs:\n    query: q\n", schemas=plain)
    config = _config(tmp_path, "location", schemas.as_uri())
    assert check_input_model_parity([tools], config, tmp_path, Severity.WARNING) == []


def test_resolver_no_candidate_entries(tmp_path: Path) -> None:
    # No input_model and no description Args → nothing to resolve.
    (tmp_path / "schemas.py").write_text(_SCHEMAS)
    tools = tmp_path / "tools.py"
    tools.write_text('TOOLS = [{"name": "x", "parameters": {"properties": {}}}]\n')
    config = _config(tmp_path, "location", (tmp_path / "schemas.py").as_uri())
    assert check_input_model_parity([tools], config, tmp_path, Severity.WARNING) == []


# --- CLI integration ----------------------------------------------------------


def _write_config(tmp_path: Path, mode: str, target_uri: str, *, select: str = "REG") -> Path:
    """Write a pyproject.toml wiring the fake LSP server; return its path."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[tool.docpact]\n"
        f"select = [{select!r}]\n\n"
        "[tool.docpact.lsp]\n"
        f"server = ['{sys.executable}', '{_FAKE}', '{mode}', '{target_uri}']\n"
    )
    return pyproject


def test_cli_crossfile_reports_reg010(tmp_path: Path) -> None:
    tools, schemas = _workspace(tmp_path, "Search.\n\nArgs:\n    query: q\n")
    pyproject = _write_config(tmp_path, "location", schemas.as_uri())
    result = CliRunner().invoke(
        main, ["check", str(tools), "--crossfile", "--config", str(pyproject)]
    )
    assert "REG010" in result.output
    assert "limit" in result.output


def test_cli_without_crossfile_does_not_run_reg010(tmp_path: Path) -> None:
    tools, schemas = _workspace(tmp_path, "Search.\n\nArgs:\n    query: q\n")
    pyproject = _write_config(tmp_path, "location", schemas.as_uri())
    result = CliRunner().invoke(main, ["check", str(tools), "--config", str(pyproject)])
    assert "REG010" not in result.output


def test_cli_crossfile_without_reg_selected_notes_and_skips(tmp_path: Path) -> None:
    tools, schemas = _workspace(tmp_path, "Search.\n\nArgs:\n    query: q\n")
    pyproject = _write_config(tmp_path, "location", schemas.as_uri(), select="DOC")
    result = CliRunner().invoke(
        main, ["check", str(tools), "--crossfile", "--config", str(pyproject)]
    )
    assert "REG010 is not enabled" in result.output
    assert "REG010" not in result.output.replace("REG010 is not enabled", "")


def test_cli_crossfile_missing_server_degrades(tmp_path: Path) -> None:
    tools, _ = _workspace(tmp_path, "Search.\n\nArgs:\n    query: q\n")
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[tool.docpact]\nselect = ['REG']\n\n"
        "[tool.docpact.lsp]\nserver = ['docpact-no-such-server-xyz']\n"
    )
    result = CliRunner().invoke(
        main, ["check", str(tools), "--crossfile", "--config", str(pyproject)]
    )
    assert "cross-file analysis skipped" in result.output
    assert result.exit_code == 0

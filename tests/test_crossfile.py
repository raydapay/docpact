"""Tests for the opt-in cross-file pass (REG010; ADR-009).

No real language server: resolution is driven against the fake server
subprocess (``tests/fixtures/fake_lsp_server.py``), pointed at real fixture
files written under tmp_path. The pure comparison (parity_findings), model
field extraction, and URI handling are unit-tested directly; the resolver and
the ``check --crossfile`` CLI path are tested end-to-end through the fake.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from click.testing import CliRunner

if TYPE_CHECKING:
    import pytest

from docpact.cli import main
from docpact.config import Config, LspConfig
from docpact.crossfile.resolver import _uri_to_path, resolve_crossfile
from docpact.model.diagnostic import Severity
from docpact.model.function_info import FunctionInfo, ParameterInfo
from docpact.model.tool_registry import ModelRef, ToolRegistryEntry
from docpact.parser.pydantic_model import model_field_names
from docpact.rules.reg.reg010_input_model_parity import parity_findings
from docpact.rules.reg.reg011_handler_signature_parity import signature_findings
from docpact.semantic.analyzer import render_function

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
    results = resolve_crossfile([tools], config, tmp_path).findings
    assert results == []


def test_resolver_reports_drift(tmp_path: Path) -> None:
    # Doc documents only 'query'; the model also has 'limit'.
    tools, schemas = _workspace(tmp_path, "Search.\n\nArgs:\n    query: q\n")
    config = _config(tmp_path, "location", schemas.as_uri())
    results = resolve_crossfile([tools], config, tmp_path).findings
    assert len(results) == 1
    assert results[0].code == "REG010"
    assert "limit" in results[0].message


def test_resolver_unresolved_is_skipped(tmp_path: Path) -> None:
    tools, schemas = _workspace(tmp_path, "Search.\n\nArgs:\n    query: q\n")
    config = _config(tmp_path, "empty", schemas.as_uri())
    config = dataclasses.replace(config, lsp=LspConfig(server=config.lsp.server, timeout=0.3))
    assert resolve_crossfile([tools], config, tmp_path).findings == []


def test_resolver_non_pydantic_target_is_skipped(tmp_path: Path) -> None:
    plain = "class SearchInput:\n    query: str\n"
    tools, schemas = _workspace(tmp_path, "Search.\n\nArgs:\n    query: q\n", schemas=plain)
    config = _config(tmp_path, "location", schemas.as_uri())
    assert resolve_crossfile([tools], config, tmp_path).findings == []


def test_resolver_no_candidate_entries(tmp_path: Path) -> None:
    # No input_model and no description Args → nothing to resolve.
    (tmp_path / "schemas.py").write_text(_SCHEMAS)
    tools = tmp_path / "tools.py"
    tools.write_text('TOOLS = [{"name": "x", "parameters": {"properties": {}}}]\n')
    config = _config(tmp_path, "location", (tmp_path / "schemas.py").as_uri())
    assert resolve_crossfile([tools], config, tmp_path).findings == []


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


# --- 5b: imported-handler Tier-3 floor (ADR-010) ------------------------------

# A handler in its own (public) file. Its docstring is complete for the Tier 2 a
# public module gets by default — Args + Returns — so without the floor it is
# clean; under the cross-file Tier-3 floor it must additionally carry Raises /
# Constraints / Stability / MCP, which it lacks.
_HANDLER_ONLY = (
    '"""Handlers."""\n\n\n'
    "def search_cases(query: str) -> list:\n"
    '    """Search cases.\n\n'
    "    Args:\n"
    "        query: The search query.\n\n"
    "    Returns:\n"
    "        The matching cases.\n"
    '    """\n'
    "    return []\n"
)


def _handler_workspace(tmp_path: Path) -> tuple[Path, Path]:
    """Write handlers.py + a registry.py registering its handler; return both paths."""
    handlers = tmp_path / "handlers.py"
    handlers.write_text(_HANDLER_ONLY)
    registry = tmp_path / "registry.py"
    registry.write_text(
        '"""Registry."""\n'
        "from handlers import search_cases\n\n\n"
        "class ToolDefinition:\n"
        "    def __init__(self, **kw):\n        pass\n\n\n"
        'TOOLS = [ToolDefinition(name="search", handler=search_cases)]\n'
    )
    return registry, handlers


def test_resolve_crossfile_floor_from_handler(tmp_path: Path) -> None:
    registry, handlers = _handler_workspace(tmp_path)
    config = _config(tmp_path, "location", handlers.as_uri())
    result = resolve_crossfile([registry], config, tmp_path)
    assert (handlers.resolve().as_posix(), "search_cases") in result.floor


def _write_reg_doc_config(tmp_path: Path, target_uri: str) -> Path:
    """pyproject selecting DOC+REG and wiring the fake server to target_uri."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[tool.docpact]\n"
        'select = ["DOC", "REG"]\n\n'
        "[tool.docpact.lsp]\n"
        f"server = ['{sys.executable}', '{_FAKE}', 'location', '{target_uri}']\n"
    )
    return pyproject


def test_cli_crossfile_floors_imported_handler(tmp_path: Path) -> None:
    registry, handlers = _handler_workspace(tmp_path)
    pyproject = _write_reg_doc_config(tmp_path, handlers.as_uri())
    args = ["check", str(handlers), str(registry), "--config", str(pyproject), "--format", "json"]

    without = CliRunner().invoke(main, args)
    with_cf = CliRunner().invoke(main, [*args, "--crossfile"])

    def _handler_findings(output: str) -> list[dict]:
        diags = json.loads(output)["diagnostics"]
        return [d for d in diags if d["location"]["file"].endswith("handlers.py")]

    # Without --crossfile, search_cases is Tier 2 and its Args/Returns suffice → clean.
    assert _handler_findings(without.output) == []
    # With --crossfile, it is floored to Tier 3 → the extra section requirements fire.
    assert _handler_findings(with_cf.output)


# --- increment 2: REG011 handler-signature parity (ADR-010) -------------------


def _handler_fn(params: tuple[ParameterInfo, ...]) -> FunctionInfo:
    """A minimal module-level FunctionInfo with the given parameters."""
    return FunctionInfo(
        name="search_cases",
        file_path=Path("impl.py"),
        line=10,
        column=0,
        parameters=params,
        return_annotation="list",
        decorators=(),
        docstring_raw="Search.",
        docstring_line=10,
        containing_class=None,
        def_start_offset=0,
        def_end_offset=0,
        docstring_start_offset=None,
        docstring_end_offset=None,
    )


def _handler_entry(**kw: object) -> ToolRegistryEntry:
    """A registry entry that names an imported handler."""
    return ToolRegistryEntry(
        name="search",
        line=8,
        column=4,
        property_keys=kw.get("property_keys"),  # type: ignore[arg-type]
        has_description=False,
        input_model_ref=ModelRef(name="SearchInput", line=8, column=40),
        handler_ref=ModelRef(name="search_cases", line=8, column=60),
    )


def _param(name: str, annotation: str | None = None, kind: str = "positional") -> ParameterInfo:
    """A ParameterInfo shorthand."""
    return ParameterInfo(name=name, annotation=annotation, default=None, kind=kind)


def test_reg011_model_field_not_accepted() -> None:
    entry = _handler_entry()
    handler = _handler_fn((_param("query", "str"),))  # missing 'limit'
    results = signature_findings(
        entry, Path("t.py"), handler, frozenset({"query", "limit"}), Severity.WARNING
    )
    assert len(results) == 1
    assert results[0].code == "REG011"
    assert "limit" in results[0].message and "does not accept" in results[0].message


def test_reg011_match_yields_nothing() -> None:
    entry = _handler_entry()
    handler = _handler_fn((_param("query", "str"), _param("limit", "int")))
    assert (
        signature_findings(
            entry, Path("t.py"), handler, frozenset({"query", "limit"}), Severity.WARNING
        )
        == []
    )


def test_reg011_skips_model_instance_handler() -> None:
    entry = _handler_entry()
    handler = _handler_fn((_param("payload", "SearchInput"),))  # takes the whole model
    assert (
        signature_findings(
            entry, Path("t.py"), handler, frozenset({"query", "limit"}), Severity.WARNING
        )
        == []
    )


def test_reg011_skips_var_keyword_handler() -> None:
    entry = _handler_entry()
    handler = _handler_fn((_param("kwargs", None, "var_keyword"),))
    assert (
        signature_findings(
            entry, Path("t.py"), handler, frozenset({"query", "limit"}), Severity.WARNING
        )
        == []
    )


def test_reg011_schema_takes_precedence_over_model() -> None:
    entry = _handler_entry(property_keys=frozenset({"query", "phantom"}))
    handler = _handler_fn((_param("query", "str"), _param("limit", "int")))
    results = signature_findings(
        entry, Path("t.py"), handler, frozenset({"query", "limit"}), Severity.WARNING
    )
    # Declared from the schema (query, phantom); 'phantom' is not accepted.
    assert [r.message for r in results if "phantom" in r.message]
    assert all("schema" in r.message for r in results)


def _impl_with_handler(tmp_path: Path, handler_src: str) -> tuple[Path, Path]:
    """Write impl.py (SearchInput{query,limit} + a handler) and a registry for it."""
    impl = tmp_path / "impl.py"
    impl.write_text(
        '"""Impl."""\n'
        "from pydantic import BaseModel\n\n\n"
        "class SearchInput(BaseModel):\n    query: str\n    limit: int\n\n\n" + handler_src
    )
    registry = tmp_path / "registry.py"
    registry.write_text(
        '"""Registry."""\n'
        "from impl import SearchInput, search_cases\n\n\n"
        "class ToolDefinition:\n    def __init__(self, **kw):\n        pass\n\n\n"
        'TOOLS = [ToolDefinition(name="search", handler=search_cases, input_model=SearchInput)]\n'
    )
    return registry, impl


def test_resolver_reg011_end_to_end(tmp_path: Path) -> None:
    # Handler accepts only 'query'; the input model also declares 'limit'.
    registry, impl = _impl_with_handler(
        tmp_path, 'def search_cases(query: str) -> list:\n    """S."""\n    return []\n'
    )
    config = _config(tmp_path, "location", impl.as_uri())
    findings = resolve_crossfile([registry, impl], config, tmp_path).findings
    reg011 = [f for f in findings if f.code == "REG011"]
    assert len(reg011) == 1 and "limit" in reg011[0].message


# --- 5d: cross-file x semantic (ADR-010) --------------------------------------

# Model and handler co-located so the single fake target URI resolves both.
_IMPL = (
    '"""Impl."""\n'
    "from pydantic import BaseModel\n\n\n"
    "class SearchInput(BaseModel):\n"
    "    query: str\n"
    "    limit: int\n\n\n"
    "def search_cases(query: str) -> list:\n"
    '    """Search cases."""\n'
    "    return []\n"
)


def _impl_workspace(tmp_path: Path) -> tuple[Path, Path]:
    """Write impl.py (model + handler) and a registry referencing both."""
    impl = tmp_path / "impl.py"
    impl.write_text(_IMPL)
    registry = tmp_path / "registry.py"
    registry.write_text(
        '"""Registry."""\n'
        "from impl import SearchInput, search_cases\n\n\n"
        "class ToolDefinition:\n"
        "    def __init__(self, **kw):\n        pass\n\n\n"
        "TOOLS = [\n"
        "    ToolDefinition(\n"
        '        name="search",\n'
        "        handler=search_cases,\n"
        "        input_model=SearchInput,\n"
        '        description="Search cases.",\n'
        "    ),\n"
        "]\n"
    )
    return registry, impl


def test_resolve_crossfile_context_carries_model_fields(tmp_path: Path) -> None:
    registry, impl = _impl_workspace(tmp_path)
    config = _config(tmp_path, "location", impl.as_uri())
    result = resolve_crossfile([registry, impl], config, tmp_path)
    note = result.context[(impl.resolve().as_posix(), "search_cases")]
    assert "search" in note  # tool name
    assert "query" in note and "limit" in note  # imported model fields
    assert "Search cases." in note  # registry description


def test_render_function_appends_context() -> None:
    fn = FunctionInfo(
        name="f",
        file_path=Path("m.py"),
        line=1,
        column=0,
        parameters=(ParameterInfo(name="x", annotation="int", default=None, kind="positional"),),
        return_annotation="str",
        decorators=(),
        docstring_raw="Summary.",
        docstring_line=1,
        containing_class=None,
        def_start_offset=0,
        def_end_offset=0,
        docstring_start_offset=None,
        docstring_end_offset=None,
    )
    assert "[cross-file contract] note here" in render_function(fn, "note here")
    assert "[cross-file contract]" not in render_function(fn, None)


def test_cli_semantic_crossfile_dry_run_scopes_and_enriches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _registry, impl = _impl_workspace(tmp_path)
    # docpact.toml so config is discovered from cwd (semantic has no --config flag).
    (tmp_path / "docpact.toml").write_text(
        f"[lsp]\nserver = ['{sys.executable}', '{_FAKE}', 'location', '{impl.as_uri()}']\n"
    )
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    # Pass the directory so the registry (registry.py) is in the resolver's scope.
    base = ["semantic", ".", "--dry-run", "--min-tier", "3"]

    without_cf = runner.invoke(main, base)
    with_cf = runner.invoke(main, [*base, "--crossfile"])

    # search_cases is Tier 2 in its own file: out of scope at --min-tier 3 without
    # --crossfile, floored to Tier 3 (so in scope) with it, and its prompt is enriched.
    assert "search_cases" not in without_cf.output
    assert "search_cases" in with_cf.output
    assert "[cross-file contract]" in with_cf.output
    assert "limit" in with_cf.output  # imported model fields injected

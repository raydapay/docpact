"""Tests for tool-registry extraction (docpact.parser.registry)."""

from __future__ import annotations

from docpact.parser.docstring import GoogleParser
from docpact.parser.registry import extract_tool_registry

_DEFAULTS = {
    "tool_classes": ("ToolDefinition",),
    "name_field": "name",
    "description_field": "description",
    "parameters_field": "parameters",
}


def _extract(source: str, **overrides: object) -> list:
    """Run extraction with default field config, applying any overrides."""
    kwargs = {**_DEFAULTS, **overrides}
    return extract_tool_registry(source, **kwargs)  # type: ignore[arg-type]


# --- constructor-call entries -------------------------------------------------


def test_constructor_entry_basic() -> None:
    src = """
BOT_TOOLS = [
    ToolDefinition(
        name="search_case",
        description="Search for cases.",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
    ),
]
"""
    entries = _extract(src)
    assert len(entries) == 1
    e = entries[0]
    assert e.name == "search_case"
    assert e.property_keys == frozenset({"query"})
    assert e.has_description is True


def test_constructor_annotated_assignment() -> None:
    src = """
BOT_TOOLS: list[ToolDefinition] = [
    ToolDefinition(name="f", parameters={"properties": {"a": {}, "b": {}}}),
]
"""
    entries = _extract(src)
    assert len(entries) == 1
    assert entries[0].property_keys == frozenset({"a", "b"})


def test_constructor_dotted_class_name_matches_on_attribute() -> None:
    src = """
TOOLS = [mod.ToolDefinition(name="f", parameters={"properties": {"x": {}}})]
"""
    entries = _extract(src)
    assert len(entries) == 1
    assert entries[0].name == "f"


def test_constructor_class_not_in_config_is_ignored() -> None:
    src = 'TOOLS = [SomethingElse(name="f", parameters={"properties": {"x": {}}})]'
    assert _extract(src) == []


def test_constructor_dynamic_name_omitted() -> None:
    src = 'TOOLS = [ToolDefinition(name=NAME, parameters={"properties": {"x": {}}})]'
    assert _extract(src) == []


def test_constructor_custom_class_name_config() -> None:
    src = 'TOOLS = [MyTool(name="f", parameters={"properties": {"x": {}}})]'
    entries = _extract(src, tool_classes=("MyTool",))
    assert len(entries) == 1
    assert entries[0].name == "f"


# --- dict-literal entries -----------------------------------------------------


def test_dict_entry_basic() -> None:
    src = """
TOOLS = [
    {
        "name": "search",
        "description": "desc",
        "parameters": {"properties": {"query": {"type": "string"}}},
    },
]
"""
    entries = _extract(src)
    assert len(entries) == 1
    assert entries[0].name == "search"
    assert entries[0].property_keys == frozenset({"query"})


def test_dict_without_parameters_key_is_ignored() -> None:
    # Requires both name and parameters to avoid matching incidental dicts.
    src = 'CONFIG = [{"name": "alice", "role": "admin"}]'
    assert _extract(src) == []


def test_dict_without_name_key_is_ignored() -> None:
    src = 'X = [{"parameters": {"properties": {"a": {}}}}]'
    assert _extract(src) == []


def test_dict_dynamic_name_omitted() -> None:
    src = "X = [{'name': some_var, 'parameters': {'properties': {}}}]"
    assert _extract(src) == []


# --- property_keys semantics --------------------------------------------------


def test_no_properties_key_yields_empty_set() -> None:
    # A schema with no properties: nothing claimed, no phantom possible.
    src = 'TOOLS = [ToolDefinition(name="f", parameters={"type": "object"})]'
    entries = _extract(src)
    assert entries[0].property_keys == frozenset()


def test_non_dict_parameters_yields_none() -> None:
    # Dynamically built schema — REG001 must skip (literals-only).
    src = 'TOOLS = [ToolDefinition(name="f", parameters=make_schema(f))]'
    entries = _extract(src)
    assert entries[0].property_keys is None


def test_non_dict_properties_yields_none() -> None:
    src = 'TOOLS = [ToolDefinition(name="f", parameters={"properties": build_props()})]'
    entries = _extract(src)
    assert entries[0].property_keys is None


def test_non_literal_property_key_yields_none() -> None:
    src = 'TOOLS = [ToolDefinition(name="f", parameters={"properties": {KEY: {}}})]'
    entries = _extract(src)
    assert entries[0].property_keys is None


def test_missing_parameters_field_yields_none() -> None:
    src = 'TOOLS = [ToolDefinition(name="f")]'
    entries = _extract(src)
    assert entries[0].property_keys is None


# --- description presence -----------------------------------------------------


def test_empty_description_is_absent() -> None:
    src = 'TOOLS = [ToolDefinition(name="f", description="", parameters={"properties": {}})]'
    assert _extract(src)[0].has_description is False


def test_computed_description_is_present() -> None:
    src = 'TOOLS = [ToolDefinition(name="f", description=DESC, parameters={"properties": {}})]'
    assert _extract(src)[0].has_description is True


def test_missing_description_is_absent() -> None:
    src = 'TOOLS = [ToolDefinition(name="f", parameters={"properties": {}})]'
    assert _extract(src)[0].has_description is False


# --- scope and locality -------------------------------------------------------


def test_function_local_registry_ignored() -> None:
    src = """
def build():
    tools = [ToolDefinition(name="f", parameters={"properties": {"x": {}}})]
    return tools
"""
    assert _extract(src) == []


def test_non_list_assignment_ignored() -> None:
    src = 'SINGLE = ToolDefinition(name="f", parameters={"properties": {"x": {}}})'
    assert _extract(src) == []


def test_mixed_list_extracts_only_entries() -> None:
    src = """
TOOLS = [
    ToolDefinition(name="a", parameters={"properties": {"x": {}}}),
    "not an entry",
    {"name": "b", "parameters": {"properties": {"y": {}}}},
    42,
]
"""
    entries = _extract(src)
    assert [e.name for e in entries] == ["a", "b"]


def test_multiple_lists_all_extracted() -> None:
    src = """
A = [ToolDefinition(name="a", parameters={"properties": {}})]
B = [ToolDefinition(name="b", parameters={"properties": {}})]
"""
    assert sorted(e.name for e in _extract(src)) == ["a", "b"]


def test_source_order_preserved() -> None:
    src = """
TOOLS = [
    ToolDefinition(name="first", parameters={"properties": {}}),
    ToolDefinition(name="second", parameters={"properties": {}}),
]
"""
    assert [e.name for e in _extract(src)] == ["first", "second"]


# --- robustness ---------------------------------------------------------------


def test_syntax_error_returns_empty() -> None:
    assert _extract("def broken(:\n") == []


def test_empty_source_returns_empty() -> None:
    assert _extract("") == []


def test_entry_location_recorded() -> None:
    src = 'TOOLS = [ToolDefinition(name="f", parameters={"properties": {"x": {}}})]'
    e = _extract(src)[0]
    assert e.line == 1
    assert e.column == 9  # position of the ToolDefinition call within the list


# --- input_model reference (cross-file; ADR-009) ------------------------------


def test_input_model_ref_captured_for_name() -> None:
    src = 'TOOLS = [\n    ToolDefinition(name="f", input_model=SearchInput),\n]'
    ref = _extract(src)[0].input_model_ref
    assert ref is not None
    assert ref.name == "SearchInput"
    assert ref.line == 2  # 1-based
    assert ref.column == src.splitlines()[1].index("SearchInput")  # 0-based


def test_input_model_ref_absent_when_field_missing() -> None:
    src = 'TOOLS = [ToolDefinition(name="f", parameters={"properties": {}})]'
    assert _extract(src)[0].input_model_ref is None


def test_input_model_ref_none_for_dynamic_expressions() -> None:
    # Attribute, call, and subscript are dynamic — no bare Name to resolve.
    for expr in ("schemas.SearchInput", "make_model()", "MODELS['search']"):
        src = f'TOOLS = [ToolDefinition(name="f", input_model={expr})]'
        assert _extract(src)[0].input_model_ref is None, expr


def test_input_model_ref_in_dict_entry() -> None:
    src = 'TOOLS = [{"name": "f", "input_model": SearchInput, "parameters": {"properties": {}}}]'
    ref = _extract(src)[0].input_model_ref
    assert ref is not None and ref.name == "SearchInput"


def test_input_model_field_is_configurable() -> None:
    src = 'TOOLS = [ToolDefinition(name="f", schema_model=SearchInput)]'
    assert _extract(src)[0].input_model_ref is None  # default field name does not match
    ref = _extract(src, input_model_field="schema_model")[0].input_model_ref
    assert ref is not None and ref.name == "SearchInput"


# --- description Args keys (cross-file; ADR-009) ------------------------------

_DESC_WITH_ARGS = """Search for cases.

Args:
    query: The search string.
    limit: Maximum number of results.
"""


def test_description_arg_keys_none_without_parser() -> None:
    src = f'TOOLS = [ToolDefinition(name="f", description={_DESC_WITH_ARGS!r})]'
    assert _extract(src)[0].description_arg_keys is None


def test_description_arg_keys_parsed_with_parser() -> None:
    src = f'TOOLS = [ToolDefinition(name="f", description={_DESC_WITH_ARGS!r})]'
    keys = _extract(src, description_parser=GoogleParser())[0].description_arg_keys
    assert keys == frozenset({"query", "limit"})


def test_description_arg_keys_empty_when_no_args_section() -> None:
    src = 'TOOLS = [ToolDefinition(name="f", description="Just a summary.")]'
    assert _extract(src, description_parser=GoogleParser())[0].description_arg_keys == frozenset()


def test_description_arg_keys_none_for_computed_description() -> None:
    src = 'TOOLS = [ToolDefinition(name="f", description=DESC)]'
    assert _extract(src, description_parser=GoogleParser())[0].description_arg_keys is None


def test_handler_ref_captured_for_name() -> None:
    src = 'TOOLS = [ToolDefinition(name="f", handler=search_cases)]'
    ref = _extract(src)[0].handler_ref
    assert ref is not None
    assert ref.name == "search_cases"
    assert ref.line == 1


def test_handler_ref_absent_when_field_missing() -> None:
    src = 'TOOLS = [ToolDefinition(name="f", parameters={"properties": {}})]'
    assert _extract(src)[0].handler_ref is None


def test_handler_ref_none_for_dynamic_expression() -> None:
    src = 'TOOLS = [ToolDefinition(name="f", handler=mod.search_cases)]'
    assert _extract(src)[0].handler_ref is None


def test_handler_field_is_configurable() -> None:
    src = 'TOOLS = [ToolDefinition(name="f", fn=search_cases)]'
    assert _extract(src)[0].handler_ref is None  # default "handler" does not match
    ref = _extract(src, handler_field="fn")[0].handler_ref
    assert ref is not None and ref.name == "search_cases"


def test_description_text_captured_for_literal() -> None:
    src = 'TOOLS = [ToolDefinition(name="f", description="A literal desc.")]'
    assert _extract(src)[0].description_text == "A literal desc."


def test_description_text_none_for_computed() -> None:
    src = "TOOLS = [ToolDefinition(name='f', description=DESC)]"
    assert _extract(src)[0].description_text is None


def test_description_arg_keys_in_dict_entry() -> None:
    src = (
        "TOOLS = [{"
        f'"name": "f", "description": {_DESC_WITH_ARGS!r}, '
        '"parameters": {"properties": {}}}]'
    )
    keys = _extract(src, description_parser=GoogleParser())[0].description_arg_keys
    assert keys == frozenset({"query", "limit"})

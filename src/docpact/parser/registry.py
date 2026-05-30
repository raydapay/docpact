"""Extract tool-registration entries from a single source file via stdlib ast.

Recognizes two co-located registration shapes inside a module-level list:

  1. A constructor call to a configured class:
         BOT_TOOLS = [ToolDefinition(name="search", description="...", parameters={...})]
  2. A raw dict literal (OpenAI/Bedrock function-calling style):
         TOOLS = [{"name": "search", "description": "...", "parameters": {...}}]

Same-file only. This module never resolves imports or follows a name to a
function in another module — it produces the literal facts present in this
file's AST and nothing else. Correlating an entry to a function is the
caller's job (a string-name match against same-file definitions). See ADR-005.

Literals-only, like DOC021: an entry whose ``name`` is not a string literal is
not produced at all (it cannot be correlated); an entry whose ``parameters``
is not a static dict literal yields ``property_keys = None`` so the REG001
cross-check is skipped rather than guessed.
"""

from __future__ import annotations

import ast

from docpact.model.tool_registry import ToolRegistryEntry


def extract_tool_registry(
    source: str,
    *,
    tool_classes: tuple[str, ...],
    name_field: str,
    description_field: str,
    parameters_field: str,
) -> list[ToolRegistryEntry]:
    """Extract tool-registration entries from module-level list literals.

    Args:
        source: Raw Python source text of one file.
        tool_classes: Constructor class names to treat as registry entries
            (e.g. ``("ToolDefinition",)``). Matched against the dotted call
            name, so both ``ToolDefinition(...)`` and ``mod.ToolDefinition(...)``
            qualify. Dict literals are always considered regardless of this.
        name_field: Field/key holding the registered function name.
        description_field: Field/key holding the tool description.
        parameters_field: Field/key holding the JSON Schema parameters object.

    Returns:
        One ToolRegistryEntry per recognized entry, in source order. Entries
        whose name is not a string literal are omitted. Returns an empty list
        if the source cannot be parsed — PARSE001 owns parse failures.

    Constraints:
        Only module-level assignments whose value is a list literal are
        inspected. Function-local and class-body registries are ignored, as
        are registries built by append/comprehension/spread (not literals).

    Stability: beta
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    entries: list[ToolRegistryEntry] = []
    class_set = frozenset(tool_classes)
    for node in tree.body:
        value = _assignment_value(node)
        if not isinstance(value, ast.List):
            continue
        for elt in value.elts:
            entry = _entry_from_element(
                elt, class_set, name_field, description_field, parameters_field
            )
            if entry is not None:
                entries.append(entry)
    return entries


def _assignment_value(node: ast.stmt) -> ast.expr | None:
    """Return the assigned value of a module-level assignment, or None.

    Handles both ``X = [...]`` (ast.Assign) and ``X: list[T] = [...]``
    (ast.AnnAssign). Returns None for any other statement.
    """
    if isinstance(node, ast.Assign):
        return node.value
    if isinstance(node, ast.AnnAssign):
        return node.value
    return None


def _entry_from_element(
    elt: ast.expr,
    class_set: frozenset[str],
    name_field: str,
    description_field: str,
    parameters_field: str,
) -> ToolRegistryEntry | None:
    """Build a ToolRegistryEntry from one list element, or None if it is not one.

    A constructor call qualifies when its dotted callee name is in class_set.
    A dict literal qualifies when it contains both the name and parameters
    keys — a strong signal it is a tool schema and not incidental data.
    """
    if isinstance(elt, ast.Call):
        return _entry_from_call(elt, class_set, name_field, description_field, parameters_field)
    if isinstance(elt, ast.Dict):
        return _entry_from_dict(elt, name_field, description_field, parameters_field)
    return None


def _entry_from_call(
    call: ast.Call,
    class_set: frozenset[str],
    name_field: str,
    description_field: str,
    parameters_field: str,
) -> ToolRegistryEntry | None:
    """Build an entry from a ``ToolDefinition(name=..., ...)`` constructor call."""
    callee = _dotted_name(call.func)
    if callee is None or callee.split(".")[-1] not in {c.split(".")[-1] for c in class_set}:
        return None
    kwargs = {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}
    name = _string_value(kwargs.get(name_field))
    if name is None:
        return None  # dynamic name — cannot correlate
    return ToolRegistryEntry(
        name=name,
        line=call.lineno,
        column=call.col_offset,
        property_keys=_property_keys(kwargs.get(parameters_field)),
        has_description=_has_nonempty_string(kwargs.get(description_field)),
    )


def _entry_from_dict(
    node: ast.Dict,
    name_field: str,
    description_field: str,
    parameters_field: str,
) -> ToolRegistryEntry | None:
    """Build an entry from a flat ``{"name": ..., "parameters": {...}}`` dict literal."""
    items = _string_keyed_items(node)
    if name_field not in items or parameters_field not in items:
        return None  # require both name and parameters to avoid matching incidental dicts
    name = _string_value(items[name_field])
    if name is None:
        return None  # dynamic name — cannot correlate
    return ToolRegistryEntry(
        name=name,
        line=node.lineno,
        column=node.col_offset,
        property_keys=_property_keys(items.get(parameters_field)),
        has_description=_has_nonempty_string(items.get(description_field)),
    )


def _property_keys(parameters: ast.expr | None) -> frozenset[str] | None:
    """Return the keys of parameters.properties, or None if not statically known.

    Returns an empty frozenset when ``parameters`` is a dict literal with no
    ``properties`` key (a schema declaring no properties — no phantom possible).
    Returns None when ``parameters`` or its ``properties`` is not a static dict
    literal, or any property key is non-literal — the REG001 check is skipped.
    """
    if not isinstance(parameters, ast.Dict):
        return None
    items = _string_keyed_items(parameters)
    properties = items.get("properties")
    if properties is None:
        return frozenset()
    if not isinstance(properties, ast.Dict):
        return None
    keys: set[str] = set()
    for key in properties.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            keys.add(key.value)
        else:
            return None  # a non-literal property key — cannot enumerate safely
    return frozenset(keys)


def _string_keyed_items(node: ast.Dict) -> dict[str, ast.expr]:
    """Return the dict's entries whose keys are string-constant literals.

    Non-string keys and ``**spread`` entries (key is None) are dropped.
    """
    items: dict[str, ast.expr] = {}
    for key, value in zip(node.keys, node.values, strict=True):
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            items[key.value] = value
    return items


def _string_value(node: ast.expr | None) -> str | None:
    """Return the value of a string-constant node, or None if not a string literal."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _has_nonempty_string(node: ast.expr | None) -> bool:
    """Return True if node is a non-empty string literal, or any non-literal expression.

    Mirrors DOC050's description handling: a computed description is accepted
    as present; only a missing field or an empty string literal counts as absent.
    """
    if node is None:
        return False
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.strip() != ""
    return True


def _dotted_name(node: ast.expr) -> str | None:
    """Return the dotted name of a callee expression, or None if not a name/attribute."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return f"{base}.{node.attr}" if base is not None else None
    return None

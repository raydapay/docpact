"""Extract tool-registration entries from a single source file via stdlib ast.

Recognizes a configured constructor class (and raw dict literals) in four
bounded module-level positions (ADR-011):

  1. An element of a module-level list literal (the original shape):
         BOT_TOOLS = [ToolDefinition(name="search", description="...", parameters={...})]
         TOOLS = [{"name": "search", "description": "...", "parameters": {...}}]
  2. An assignment value:        SPEC = ToolSpec(name="search", ...)
  3. A bare expression statement: ToolSpec(name="search", ...)
  4. A direct argument to a module-level call (the builder idiom):
         register_tool(ToolSpec(name="search", ...))

Recursion is bounded to exactly these positions: docpact descends one level into
a wrapping call's arguments (and into a list argument's elements) but no further
— not into nested calls beyond one level, comprehensions, conditionals, loops,
or function bodies. Raw dict literals are recognized only as list elements or as
a call argument, never as a bare/assigned statement.

Same-file only. This module never resolves imports or follows a name to a
function in another module — it produces the literal facts present in this
file's AST and nothing else. Correlating an entry to a function is the
caller's job (a string-name match against same-file definitions). See ADR-005.

Literals-only, like DOC021: an entry whose ``name`` is not a string literal is
not produced at all (it cannot be correlated); an entry whose ``parameters``
is not a static dict literal yields ``property_keys = None`` so the REG001
cross-check is skipped rather than guessed. A ``description`` given as a bare
``Name`` bound once to a module-level string literal is resolved through that
single hop (ADR-011); anything else (an f-string, a call, a multiply-bound or
imported name) stays unresolved, exactly as a non-literal would.

Two further facts are captured for the opt-in cross-file pass (ADR-009), and
only when statically present: the ``input_model`` reference (a bare ``Name``,
with its source position, so LSP go-to-definition can resolve the model's
defining file) and the ``Args:`` keys of the entry's description string (parsed
by a supplied docstring parser). Both are absent (None) otherwise, so same-file
REG behaviour is unchanged.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING

from docpact.model.tool_registry import ModelRef, ToolRegistryEntry

if TYPE_CHECKING:
    from docpact.parser.docstring import DocstringParser


@dataclass(frozen=True, slots=True)
class _Fields:
    """The configured field names plus the optional description parser.

    Bundled so the recursive element helpers take one context argument rather
    than five parallel parameters.
    """

    name: str
    description: str
    parameters: str
    input_model: str
    handler: str
    parser: DocstringParser | None
    string_constants: dict[str, ast.expr]  # module-level NAME -> single string-literal binding


def extract_tool_registry(
    source: str,
    *,
    tool_classes: tuple[str, ...],
    name_field: str,
    description_field: str,
    parameters_field: str,
    input_model_field: str = "input_model",
    handler_field: str = "handler",
    description_parser: DocstringParser | None = None,
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
        input_model_field: Field/key holding the input-model reference. When
            its value is a bare ``Name``, the entry's ``input_model_ref`` is
            populated with that symbol and its position (ADR-009).
        handler_field: Field/key holding the handler reference. When its value
            is a bare ``Name``, the entry's ``handler_ref`` is populated with
            that symbol and its position (ADR-010 FR-2(b)).
        description_parser: Parser used to read the description's ``Args:``
            keys into ``description_arg_keys``. When None, that field stays
            None and no description parsing is attempted.

    Returns:
        One ToolRegistryEntry per recognized entry, in source order. Entries
        whose name is not a string literal are omitted. Returns an empty list
        if the source cannot be parsed — PARSE001 owns parse failures.

    Constraints:
        Only module-level statements are inspected, in the four bounded
        positions listed in the module docstring (list element, assignment
        value, bare expression, direct call argument). Function-local and
        class-body registries are ignored, as are registries built by
        comprehension/spread or nested more than one call deep (not literals).

    Stability: beta
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    fields = _Fields(
        name=name_field,
        description=description_field,
        parameters=parameters_field,
        input_model=input_model_field,
        handler=handler_field,
        parser=description_parser,
        string_constants=_string_constants(tree),
    )
    entries: list[ToolRegistryEntry] = []
    class_set = frozenset(tool_classes)
    for node in tree.body:
        value = _statement_expr(node)
        if value is None:
            continue
        for elt in _candidate_elements(value, class_set):
            entry = _entry_from_element(elt, class_set, fields)
            if entry is not None:
                entries.append(entry)
    return entries


def _statement_expr(node: ast.stmt) -> ast.expr | None:
    """Return the inspectable expression of a module-level statement, or None.

    Covers the three statement forms that can carry a registry entry: a bare
    expression (``register_tool(...)``), an assignment (``X = ...``), and an
    annotated assignment (``X: T = ...``). Returns None for any other statement
    and for an annotated assignment with no value.
    """
    if isinstance(node, ast.Expr):
        return node.value
    if isinstance(node, ast.Assign):
        return node.value
    if isinstance(node, ast.AnnAssign):
        return node.value
    return None


def _candidate_elements(value: ast.expr, class_set: frozenset[str]) -> list[ast.expr]:
    """Return the candidate entry nodes reachable from a statement expression.

    Bounded to one level of nesting (ADR-011): a list yields its elements; a
    configured constructor call is itself a candidate; any other call (a
    wrapper such as ``register_tool``) yields the constructor/dict nodes among
    its direct arguments, descending one further level into a list argument.
    """
    if isinstance(value, ast.List):
        return list(value.elts)
    if not isinstance(value, ast.Call):
        return []
    if _is_tool_constructor(value, class_set):
        return [value]
    # A wrapping call (e.g. register_tool(...)): inspect its direct arguments
    # one level, plus the elements of a list argument.
    candidates: list[ast.expr] = []
    for arg in (*value.args, *(kw.value for kw in value.keywords)):
        if isinstance(arg, ast.List):
            candidates.extend(arg.elts)
        elif isinstance(arg, (ast.Call, ast.Dict)):
            candidates.append(arg)
    return candidates


def _is_tool_constructor(call: ast.Call, class_set: frozenset[str]) -> bool:
    """Return True if a call's dotted callee matches a configured class name.

    Matches on the final dotted component, so both ``ToolSpec(...)`` and
    ``mod.ToolSpec(...)`` qualify when ``ToolSpec`` is configured.
    """
    callee = _dotted_name(call.func)
    if callee is None:
        return False
    return callee.split(".")[-1] in {c.split(".")[-1] for c in class_set}


def _string_constants(tree: ast.Module) -> dict[str, ast.expr]:
    """Map each module-level name bound exactly once to a string literal.

    Builds the resolution table for indirect descriptions (ADR-011): a bare
    ``Name`` description is resolved through this single hop. A name assigned
    more than once at module level — by any combination of ``=``, ``: T =``, or
    augmented assignment — is ambiguous and excluded, so only an unambiguous
    single binding to a string literal is resolvable. Tuple-unpacking and
    non-string bindings are not collected.
    """
    table: dict[str, ast.expr] = {}
    seen: set[str] = set()

    def _bind(name: str, value: ast.expr | None) -> None:
        """Record a binding; a second binding of the same name drops it as ambiguous."""
        if name in seen:  # second binding — ambiguous, drop any resolvable value
            table.pop(name, None)
            return
        seen.add(name)
        if value is not None and isinstance(value, ast.Constant) and isinstance(value.value, str):
            table[name] = value

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    _bind(target.id, node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            _bind(node.target.id, node.value)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            _bind(node.target.id, None)  # += etc. is a rebind: mark ambiguous
    return table


def _resolve_description(node: ast.expr | None, fields: _Fields) -> ast.expr | None:
    """Resolve a bare-Name description through one hop to its string literal.

    Returns the bound string-literal node when ``node`` is a ``Name`` present in
    the module's single-binding string-constant table; otherwise returns ``node``
    unchanged. The downstream description helpers then see a literal exactly as
    if it had been written inline.
    """
    if isinstance(node, ast.Name):
        return fields.string_constants.get(node.id, node)
    return node


def _entry_from_element(
    elt: ast.expr,
    class_set: frozenset[str],
    fields: _Fields,
) -> ToolRegistryEntry | None:
    """Build a ToolRegistryEntry from one list element, or None if it is not one.

    A constructor call qualifies when its dotted callee name is in class_set.
    A dict literal qualifies when it contains both the name and parameters
    keys — a strong signal it is a tool schema and not incidental data.
    """
    if isinstance(elt, ast.Call):
        return _entry_from_call(elt, class_set, fields)
    if isinstance(elt, ast.Dict):
        return _entry_from_dict(elt, fields)
    return None


def _entry_from_call(
    call: ast.Call,
    class_set: frozenset[str],
    fields: _Fields,
) -> ToolRegistryEntry | None:
    """Build an entry from a ``ToolDefinition(name=..., ...)`` constructor call."""
    if not _is_tool_constructor(call, class_set):
        return None
    kwargs = {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}
    name = _string_value(kwargs.get(fields.name))
    if name is None:
        return None  # dynamic name — cannot correlate
    description = _resolve_description(kwargs.get(fields.description), fields)
    return ToolRegistryEntry(
        name=name,
        line=call.lineno,
        column=call.col_offset,
        property_keys=_property_keys(kwargs.get(fields.parameters)),
        has_description=_has_nonempty_string(description),
        input_model_ref=_model_ref(kwargs.get(fields.input_model)),
        description_arg_keys=_description_arg_keys(description, fields.parser),
        handler_ref=_model_ref(kwargs.get(fields.handler)),
        description_text=_string_value(description),
    )


def _entry_from_dict(
    node: ast.Dict,
    fields: _Fields,
) -> ToolRegistryEntry | None:
    """Build an entry from a flat ``{"name": ..., "parameters": {...}}`` dict literal."""
    items = _string_keyed_items(node)
    if fields.name not in items or fields.parameters not in items:
        return None  # require both name and parameters to avoid matching incidental dicts
    name = _string_value(items[fields.name])
    if name is None:
        return None  # dynamic name — cannot correlate
    description = _resolve_description(items.get(fields.description), fields)
    return ToolRegistryEntry(
        name=name,
        line=node.lineno,
        column=node.col_offset,
        property_keys=_property_keys(items.get(fields.parameters)),
        has_description=_has_nonempty_string(description),
        input_model_ref=_model_ref(items.get(fields.input_model)),
        description_arg_keys=_description_arg_keys(description, fields.parser),
        handler_ref=_model_ref(items.get(fields.handler)),
        description_text=_string_value(description),
    )


def _model_ref(node: ast.expr | None) -> ModelRef | None:
    """Return the input-model reference for a bare Name node, or None.

    Only a bare ``ast.Name`` is captured — the realistic ``input_model=Model``
    shape the cross-file pass resolves (ADR-009). Attribute, call, and
    subscript expressions are treated as dynamic and skipped.
    """
    if isinstance(node, ast.Name):
        return ModelRef(name=node.id, line=node.lineno, column=node.col_offset)
    return None


def _description_arg_keys(
    node: ast.expr | None, parser: DocstringParser | None
) -> frozenset[str] | None:
    """Return the Args: keys parsed from a string-literal description.

    Returns None when no parser was supplied or the description is not a static
    string literal (it cannot be parsed); an empty frozenset when the
    description parses but has no Args section; otherwise the section's keys
    with any ``*``/``**`` prefix stripped (matching DOC007).
    """
    if parser is None:
        return None
    text = _string_value(node)
    if text is None:
        return None
    args = parser.parse(text).sections.get("Args")
    if args is None:
        return frozenset()
    return frozenset(entry.key.lstrip("*") for entry in args.entries)


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

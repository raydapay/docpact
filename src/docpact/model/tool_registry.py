"""Tool-registry entry metadata extracted from source.

Represents a single programmatic tool-registration entry — a
``ToolDefinition(name=..., description=..., parameters={...})`` constructor
call or an equivalent ``{"name": ..., "description": ..., "parameters": {...}}``
dict literal — appearing in a module-level list.

Built by docpact.parser.registry; consumed by the REG rules and by the
Tier 3 floor in tier assignment. The same-file REG rules read only the
literal facts in this file's AST (see ADR-005); the optional
``input_model_ref``/``description_arg_keys`` fields additionally feed the
opt-in cross-file pass, which resolves the referenced model via LSP (ADR-009).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelRef:
    """A reference to an imported symbol named by a tool-registry entry.

    Captures where, in *this* file, an entry names an imported symbol — its
    input model (``ToolSpec(input_model=SearchInput)``, ADR-009 FR-1) or its
    handler (``ToolDefinition(handler=search_cases)``, ADR-010 FR-2(b)). The
    position lets the cross-file pass fire ``textDocument/definition`` at the
    reference to resolve the symbol's defining file. Positions follow docpact's
    model convention — ``line`` is 1-based, ``column`` 0-based — so a caller
    targeting an LSP server (0-based line) must subtract 1 from ``line``.

    Only a bare ``Name`` reference is captured; attribute, call, and subscript
    references are treated as dynamic and yield no ModelRef.
    """

    name: str  # the referenced symbol, e.g. "SearchInput" or "search_cases"
    line: int  # 1-based line of the reference
    column: int  # 0-based column of the reference


@dataclass(frozen=True, slots=True)
class ToolRegistryEntry:
    """A single tool-registration entry as observed in source.

    Only statically-evaluable entries are produced: ``name`` is always a
    string literal (entries with a dynamic name are not extracted, since
    they cannot be correlated to a function). ``property_keys`` is None when
    the ``parameters`` schema is not a static dict literal — the REG001
    cross-check is skipped for such entries, the same literals-only
    discipline DOC021 applies to default values.

    The remaining fields support the opt-in cross-file pass (ADR-009/ADR-010)
    and are absent (None) for same-file-only use:
    ``input_model_ref`` / ``handler_ref`` are the imported model / handler
    references + position (None unless a bare Name was given for the configured
    field); ``description_arg_keys`` is the set of ``Args:`` keys parsed from
    the entry's description string (None when there is no static string
    description or no parser was supplied; an empty set when the description has
    no Args); ``description_text`` is the entry's static description string
    itself (None when it is absent or not a literal), used to enrich the
    semantic prompt with the registry's own description (ADR-010).
    """

    name: str  # value of the name field — the function this entry registers
    line: int  # 1-based line of the entry node (for diagnostics)
    column: int  # 0-based column of the entry node
    property_keys: frozenset[str] | None  # keys of parameters.properties; None if not static
    has_description: bool  # whether a non-empty description field is present (REG050, reserved)
    input_model_ref: ModelRef | None = None  # imported input-model reference (ADR-009)
    description_arg_keys: frozenset[str] | None = None  # Args: keys from the description (ADR-009)
    handler_ref: ModelRef | None = None  # imported handler reference (ADR-010 FR-2(b))
    description_text: str | None = None  # the static description string, if literal (ADR-010)

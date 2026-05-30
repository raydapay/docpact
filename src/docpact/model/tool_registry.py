"""Tool-registry entry metadata extracted from source.

Represents a single programmatic tool-registration entry — a
``ToolDefinition(name=..., description=..., parameters={...})`` constructor
call or an equivalent ``{"name": ..., "description": ..., "parameters": {...}}``
dict literal — appearing in a module-level list.

Built by docpact.parser.registry; consumed by the REG rules and by the
Tier 3 floor in tier assignment. Same-file only: the entry carries no
reference to where its named function is defined. See ADR-005.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolRegistryEntry:
    """A single tool-registration entry as observed in source.

    Only statically-evaluable entries are produced: ``name`` is always a
    string literal (entries with a dynamic name are not extracted, since
    they cannot be correlated to a function). ``property_keys`` is None when
    the ``parameters`` schema is not a static dict literal — the REG001
    cross-check is skipped for such entries, the same literals-only
    discipline DOC021 applies to default values.
    """

    name: str  # value of the name field — the function this entry registers
    line: int  # 1-based line of the entry node (for diagnostics)
    column: int  # 0-based column of the entry node
    property_keys: frozenset[str] | None  # keys of parameters.properties; None if not static
    has_description: bool  # whether a non-empty description field is present (REG050, reserved)

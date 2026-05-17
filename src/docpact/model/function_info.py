"""Function metadata extracted from source.

Represents everything the rule engine needs to know about a function
without re-parsing its source. Built by the source scanner; consumed by
tier assignment and by rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class ParameterInfo:
    """Single function parameter as observed in the signature."""

    name: str
    annotation: str | None  # source text of annotation, None if unannotated
    default: str | None  # source text of default value, None if no default
    kind: str  # "positional" | "keyword" | "var_positional" | "var_keyword" | "bound"
    # "bound": first positional parameter of an instance/class method (self, cls).
    # Bound parameters are excluded from Args documentation requirements.


@dataclass(frozen=True, slots=True)
class DecoratorInfo:
    """Single decorator application."""

    name: str  # e.g., "mcp.tool", "app.get", "staticmethod"
    arguments: dict[str, str] = field(default_factory=dict)
    # Source text of keyword arguments, by name. Used to detect
    # description= conflicts with docstring MCP: section (MCP001).


@dataclass(frozen=True, slots=True)
class FunctionInfo:
    """Function as extracted from source.

    Built by docpact.parser.source. Contains the information rules need
    to validate the function's docstring against its signature and
    decorators.
    """

    name: str
    file_path: Path
    line: int
    column: int
    parameters: tuple[ParameterInfo, ...]
    return_annotation: str | None
    decorators: tuple[DecoratorInfo, ...]
    docstring_raw: str | None  # the raw docstring text, None if absent
    docstring_line: int  # line number where the docstring begins
    containing_class: str | None  # name of containing class, None if module-level
    # Byte offsets into the source file. Computed during parsing (one O(file)
    # line-offset table pass). Used by the fix engine to generate Fix objects
    # without re-parsing. ast.col_offset is in characters; we store bytes to
    # be correct for non-ASCII source.
    def_start_offset: int  # byte offset where the `def` keyword begins
    def_end_offset: int  # byte offset after the `:` that ends the def line
    docstring_start_offset: int | None  # byte offset of opening quote; None if absent
    docstring_end_offset: int | None  # byte offset after closing quote; None if absent

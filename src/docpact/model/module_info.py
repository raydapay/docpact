"""Module-level metadata for the semantic layer (SEM002; ADR-013).

The unit SEM002 judges: a module docstring plus the module's public top-level
symbols. SEM002 checks the docstring for *scope* (purpose consistent with the
symbols — never completeness) and *orientation* (contentful, not boilerplate).
Built by docpact.parser.source.extract_module_info; frozen data, no behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class ModuleInfo:
    """A module's docstring and its public top-level symbols.

    Attributes:
        file_path: Path to the module's source file.
        docstring_raw: The module docstring as stored in the AST (no dedent).
        symbols: ``name — summary`` for each public (non-underscore) top-level
            function/class, in source order. Summary is the symbol's own
            docstring first line, or ``(no docstring)``.
    """

    file_path: Path
    docstring_raw: str
    symbols: tuple[str, ...]

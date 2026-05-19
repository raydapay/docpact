"""Parsed docstring representation.

Format-independent. Produced by any concrete DocstringParser
implementation (Google in v0.1, NumPy in v0.2, see spec §7.2).

Rules operate on this representation and never on raw docstring text.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SectionEntry:
    """One entry in a structured section (Args, Raises, See Also)."""

    key: str  # parameter name, exception type, etc.
    description: str
    type_annotation: str | None = None  # inline type from x(int): form; None when absent


@dataclass(frozen=True, slots=True)
class Section:
    """A docstring section.

    Sections fall into two shapes:
    - Structured (Args, Raises, See Also): a list of key/description entries.
    - Freeform (Notes, Alternatives, MCP, Constraints body): a single
      body of text.

    Some sections may have both (e.g., a Constraints section with multiple
    independent statements). These are represented as entries with empty keys.
    """

    name: str
    entries: tuple[SectionEntry, ...] = field(default_factory=tuple)
    body: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedDocstring:
    """A docstring parsed into its structural form.

    The raw text is preserved to support --fix operations that need to
    edit the source rather than regenerate the docstring from this
    representation.
    """

    summary: str
    description: str | None  # extended description before first section
    sections: dict[str, Section]
    raw: str

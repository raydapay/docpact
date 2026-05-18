"""Docstring parsing via griffe.

Implements the DocstringParser interface (spec §7.2) for Google and NumPy
styles. A Sphinx implementation is not on the current roadmap.

Why griffe:
    See ADR-001 §"Rationale" — griffe handles Google, NumPy, and Sphinx
    parsing with sufficient quality to power mkdocstrings. Adopting it
    eliminates the largest single chunk of implementation work for v0.1.

Why not parse docstrings ourselves:
    Considered. A custom parser would give us tighter control over edge
    cases (irregular indentation, mid-section blank lines, embedded code
    blocks). The cost is high and griffe handles these cases adequately.
    Revisit if griffe stability becomes a problem (ADR-001 revisit
    trigger 5).
"""

from __future__ import annotations

import inspect
import re
from typing import Protocol

import griffe

from docpact.model.parsed_docstring import ParsedDocstring, Section, SectionEntry

# Griffe lowercases admonition section names and hyphenates multi-word names.
# Map them back to the canonical names used throughout docpact.
_ADMONITION_TO_SECTION: dict[str, str] = {
    "constraints": "Constraints",
    "mutates": "Mutates",
    "mcp": "MCP",
    "notes": "Notes",
    # NumPy parser emits "note" (singular) for the Notes section.
    "note": "Notes",
    "alternatives": "Alternatives",
    "references": "References",
    "see-also": "See Also",
    "see also": "See Also",
    "stability": "Stability",
}

# Pattern for the inline Stability field: "Stability: stable" on its own line.
# Griffe doesn't recognize this as a section header because the value follows
# the colon on the same line rather than appearing indented on the next line.
_STABILITY_RE = re.compile(r"(?m)^Stability:\s*(?P<value>stable|beta|internal|deprecated)\s*$")

# Sections that griffe parses structurally but silently drops when the body
# consists solely of "None." (canonical empty form). After griffe parsing we
# scan the cleaned docstring for these patterns and recover them.
_NONE_BODY_RE = re.compile(r"(?m)^(?P<name>Args|Parameters|Raises):\s*\n[ \t]+None\.\s*(?:\n|$)")


class DocstringParser(Protocol):
    """Format-specific docstring parser.

    Implementations: GoogleParser (v0.1), NumPyParser (v0.2),
    SphinxParser (not on roadmap).
    """

    def parse(self, raw: str) -> ParsedDocstring:
        """Parse raw docstring text into structured form.

        Args:
            raw: The docstring as it appears in source, with surrounding
                triple-quotes stripped and dedented.

        Returns:
            ParsedDocstring with sections extracted.

        Constraints:
            Does not validate content. Parsing produces a structural
            representation; validation is the rule engine's
            responsibility.

        Stability: beta
        """
        ...

    def format_name(self) -> str:
        """Return the format identifier ('google', 'numpy', 'sphinx').

        Returns:
            Format name string, e.g. 'google'.
        """
        ...


def _sections_from_griffe(
    griffe_sections: list[griffe.DocstringSection],
    cleaned: str,
    *,
    recover_none_bodies: bool = True,
) -> tuple[str, str | None, dict[str, Section]]:
    """Convert griffe section list into (summary, description, sections).

    Shared by GoogleParser and NumpyParser. The griffe parse functions
    return the same DocstringSection types regardless of style; only the
    input syntax and the recover_none_bodies behaviour differ.

    Args:
        griffe_sections: Sections returned by griffe.parse_google or
            griffe.parse_numpy.
        cleaned: The cleaned docstring text (for None-body recovery).
        recover_none_bodies: When True, scan cleaned for "Args: None."
            patterns that griffe drops silently (Google style). NumPy
            style does not use this form; pass False to skip.

    Returns:
        Tuple of (summary, description_or_None, section_dict).
    """
    summary = ""
    description: str | None = None
    sections: dict[str, Section] = {}

    for i, gs in enumerate(griffe_sections):
        if gs.kind == griffe.DocstringSectionKind.text:
            text = gs.value.strip()
            if i == 0:
                parts = text.split("\n\n", 1)
                summary = parts[0].strip()
                if len(parts) > 1:
                    desc_text = _STABILITY_RE.sub("", parts[1]).strip()
                    if desc_text:
                        description = desc_text
            m = _STABILITY_RE.search(text)
            if m:
                sections["Stability"] = Section(name="Stability", body=m.group("value"))

        elif gs.kind == griffe.DocstringSectionKind.parameters:
            entries = tuple(
                SectionEntry(key=p.name, description=p.description or "") for p in gs.value
            )
            sections["Args"] = Section(name="Args", entries=entries)

        elif gs.kind == griffe.DocstringSectionKind.raises:
            entries = tuple(
                SectionEntry(key=r.annotation or "", description=r.description or "")
                for r in gs.value
            )
            sections["Raises"] = Section(name="Raises", entries=entries)

        elif gs.kind == griffe.DocstringSectionKind.returns:
            body = "\n".join(r.description for r in gs.value if r.description) or None
            sections["Returns"] = Section(name="Returns", body=body)

        elif gs.kind == griffe.DocstringSectionKind.examples:
            body = "\n".join(text for _, text in gs.value)
            sections["Examples"] = Section(name="Examples", body=body if len(body) > 0 else None)

        elif gs.kind == griffe.DocstringSectionKind.admonition:
            ann: str = gs.value.annotation
            section_name = _ADMONITION_TO_SECTION.get(ann)
            if section_name is None:
                section_name = ann.replace("-", " ").title()
            sections[section_name] = Section(
                name=section_name,
                body=gs.value.description or None,
            )

    if recover_none_bodies:
        for m in _NONE_BODY_RE.finditer(cleaned):
            raw_name = m.group("name")
            sec_name = "Args" if raw_name in ("Args", "Parameters") else raw_name
            if sec_name not in sections:
                sections[sec_name] = Section(name=sec_name, body="None.")

    return summary, description, sections


class GoogleParser:
    """Google-style docstring parser, backed by griffe."""

    def parse(self, raw: str) -> ParsedDocstring:
        """Parse a Google-style docstring.

        Args:
            raw: Raw docstring text (triple quotes already stripped).

        Returns:
            Parsed representation with summary, optional extended
            description, and a section dict.

        Stability: beta
        """
        cleaned = inspect.cleandoc(raw)
        doc = griffe.Docstring(cleaned)
        griffe_sections = griffe.parse_google(
            doc,
            warn_unknown_params=False,
            warn_missing_types=False,
            warnings=False,
        )
        summary, description, sections = _sections_from_griffe(
            griffe_sections, cleaned, recover_none_bodies=True
        )
        return ParsedDocstring(summary=summary, description=description, sections=sections, raw=raw)

    def format_name(self) -> str:
        """Return the format identifier for this parser.

        Returns:
            Always 'google' for this implementation.
        """
        return "google"


class NumpyParser:
    """NumPy-style docstring parser, backed by griffe.

    Handles the NumPy docstring convention where sections are introduced
    by a header line followed by a dashes underline:

        Parameters
        ----------
        x : int
            Description of x.

        Returns
        -------
        dict
            The result.

    Section mapping to docpact canonical names:

        NumPy section    → docpact canonical
        Parameters       → Args
        Returns          → Returns
        Raises           → Raises
        Notes / Note     → Notes (admonition)
        Examples         → Examples
        See Also         → See Also (admonition)
        Stability: value → Stability (inline field, same as Google)

    The ``None.`` body-recovery pass used by GoogleParser is skipped here:
    NumPy style does not express empty sections with ``None.`` prose.
    """

    def parse(self, raw: str) -> ParsedDocstring:
        """Parse a NumPy-style docstring.

        Args:
            raw: Raw docstring text (triple quotes already stripped).

        Returns:
            Parsed representation with summary, optional extended
            description, and a section dict.

        Stability: beta
        """
        cleaned = inspect.cleandoc(raw)
        doc = griffe.Docstring(cleaned)
        griffe_sections = griffe.parse_numpy(
            doc,
            warn_unknown_params=False,
            warn_missing_types=False,
            warnings=False,
        )
        summary, description, sections = _sections_from_griffe(
            griffe_sections, cleaned, recover_none_bodies=False
        )
        return ParsedDocstring(summary=summary, description=description, sections=sections, raw=raw)

    def format_name(self) -> str:
        """Return the format identifier for this parser.

        Returns:
            Always 'numpy' for this implementation.
        """
        return "numpy"

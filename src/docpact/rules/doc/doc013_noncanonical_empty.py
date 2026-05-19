"""DOC013 — Empty docstring section uses non-canonical form.

The canonical form for a section with nothing to document is "None."
(a single sentence explicitly stating absence). Non-canonical forms
include blank bodies, "N/A", "None" without the trailing period, and
equivalent abbreviations. The safe fix replaces the body with "None.".

Only fires for sections that griffe parsed and stored with a non-canonical
body. Structured sections (Args, Raises) whose content griffe cannot parse
are typically dropped silently; those are caught by DOC012 instead.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from docpact.model.diagnostic import Fix, RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring

# Non-canonical empty forms that DOC013 catches (compared case-insensitively after strip).
# The empty string case ("") is detected but not auto-fixed: there is no text to locate
# in the source, so the byte range cannot be computed without restructuring the section.
_NON_CANONICAL: frozenset[str] = frozenset({"n/a", "na", "none", ""})


def _compute_fix(
    func: FunctionInfo,
    doc: ParsedDocstring,
    section_name: str,
    body: str,
) -> Fix | None:
    """Return a Fix that replaces the non-canonical body with 'None.', or None.

    Searches doc.raw (the verbatim docstring content between the triple quotes)
    for the section header followed by the body text. The byte offset of the
    body in the source file is: docstring_start_offset + 3 (triple-quote prefix)
    + UTF-8 byte length of the content before the match.

    Returns None when the section cannot be located (e.g. missing start offset,
    blank body with no text to find, or no match in doc.raw).
    """
    if func.docstring_start_offset is None or not body:
        return None

    pattern = re.compile(
        rf"(?m)^([ \t]*{re.escape(section_name)}:[ \t]*\n[ \t]+)({re.escape(body)})([ \t]*$)",
        re.IGNORECASE,
    )
    match = pattern.search(doc.raw)
    if match is None:
        return None

    # doc.raw is the string value between the triple quotes.  The opening """ adds
    # 3 bytes at docstring_start_offset before the content begins.
    prefix_len = 3
    char_start = match.start(2)
    char_end = match.end(2)
    byte_start = (
        func.docstring_start_offset + prefix_len + len(doc.raw[:char_start].encode("utf-8"))
    )
    byte_end = func.docstring_start_offset + prefix_len + len(doc.raw[:char_end].encode("utf-8"))
    return Fix(
        description="Replace non-canonical empty body with 'None.'",
        file_path=func.file_path,
        start_offset=byte_start,
        end_offset=byte_end,
        replacement="None.",
    )


@register(
    RuleMetadata(
        code="DOC013",
        namespace="DOC",
        summary="Empty section uses non-canonical form; should be 'None.'",
        default_severity=Severity.WARNING,
        fixable=True,
        unsafe_fixable=False,
    )
)
def check(
    func: FunctionInfo,
    doc: ParsedDocstring | None,
    config: RuleConfig,
) -> list[RuleResult]:
    """Check that empty sections use the canonical 'None.' form."""
    if doc is None:
        return []

    results: list[RuleResult] = []
    loc = SourceLocation(file_path=func.file_path, line=func.line, column=func.column)

    for name, section in doc.sections.items():
        if section.entries:
            continue
        body = (section.body or "").strip()
        if body == "None.":
            continue
        if body.lower() in _NON_CANONICAL:
            fix = _compute_fix(func, doc, name, body)
            results.append(
                RuleResult(
                    code="DOC013",
                    severity=config.severity,
                    message=f"Section '{name}' uses non-canonical empty form; use 'None.' instead",
                    location=loc,
                    fix=fix,
                )
            )

    return results

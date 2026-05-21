"""DOC052 — Examples section absent when require_examples_min_tier is set.

Fires when a function's tier is >= require_examples_min_tier (from config)
and the docstring has no Examples: section.

Default off: the rule only activates when require_examples_min_tier is set
in [tool.docpact]. Intended for MCP-first codebases where Examples: is the
highest-signal section for tool-calling agents (set to 3), or for teams that
want Examples: across all public API (set to 2).

The safe fix appends an Examples: stub with a [FILL] marker at the end of
the docstring body by replacing the closing triple-quote.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docpact.model.diagnostic import Fix, RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring


@register(
    RuleMetadata(
        code="DOC052",
        namespace="DOC",
        summary="Examples section absent (require_examples_min_tier is set)",
        default_severity=Severity.ERROR,
        fixable=True,
        unsafe_fixable=False,
    )
)
def check(
    func: FunctionInfo,
    doc: ParsedDocstring | None,
    config: RuleConfig,
) -> list[RuleResult]:
    """Check that an Examples section is present when the config requires it."""
    if doc is None:
        return []

    min_tier = config.options.get("require_examples_min_tier")  # ty: ignore[invalid-argument-type]
    if min_tier is None:
        return []

    tier = int(config.options.get("tier", 2))  # ty: ignore[invalid-argument-type]
    if tier < int(min_tier):  # ty: ignore[invalid-argument-type]
        return []

    if "Examples" in doc.sections:
        return []

    fix: Fix | None = None
    if func.docstring_end_offset is not None:
        doc_indent = " " * (func.column + 4)
        inner_indent = " " * (func.column + 8)
        stub = f'\n\n{doc_indent}Examples:\n{inner_indent}[FILL]\n{doc_indent}"""'
        fix = Fix(
            description="Insert Examples: stub",
            file_path=func.file_path,
            # Replace the closing """ (3 bytes) with stub + new closing """.
            start_offset=func.docstring_end_offset - 3,
            end_offset=func.docstring_end_offset,
            replacement=stub,
        )

    return [
        RuleResult(
            code="DOC052",
            severity=config.severity,
            message=f"Tier {tier} function missing Examples section",
            location=SourceLocation(
                file_path=func.file_path,
                line=func.line,
                column=func.column,
            ),
            fix=fix,
        )
    ]

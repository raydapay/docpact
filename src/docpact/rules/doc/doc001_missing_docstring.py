"""DOC001 — missing docstring on a function that requires one.

Fires when a function's tier requires a docstring (all tiers require at
minimum a summary) and no docstring is present.

The safe fix inserts a tier-appropriate stub with [FILL] markers. The stub
itself fails DOC099 (placeholder not replaced) so it cannot pass the pipeline
unmodified — it is a starting point, not a finished docstring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docpact.model.diagnostic import Fix, RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring


def _stub_docstring(func: FunctionInfo, tier: int) -> str:
    """Build a stub docstring text containing FILL markers for insertion at def_end_offset."""
    indent = " " * (func.column + 4)
    inner = " " * (func.column + 8)
    summary = "[FILL: single-sentence summary in imperative mood]"

    # Tier 1 requires summary only.
    if tier == 1:
        return f'{indent}"""{summary}"""\n'

    # Params to document: everything except the bound receiver (self/cls).
    doc_params = [p for p in func.parameters if p.kind != "bound"]

    has_return = bool(func.return_annotation and func.return_annotation.strip() not in ("None", ""))

    sections: list[str] = []

    if doc_params:
        param_lines = "\n".join(f"{inner}{p.name}: [FILL]" for p in doc_params)
        sections.append(f"{indent}Args:\n{param_lines}")

    if has_return:
        sections.append(f"{indent}Returns:\n{inner}[FILL]")

    if tier >= 3:
        sections.append(f"{indent}Raises:\n{inner}[FILL]")
        sections.append(f"{indent}Constraints:\n{inner}[FILL]")
        sections.append(f"{indent}Stability: [FILL]")
        sections.append(f"{indent}MCP:\n{inner}[FILL]")

    if not sections:
        return f'{indent}"""{summary}"""\n'

    body = "\n\n".join(sections)
    return f'{indent}"""{summary}\n\n{body}\n{indent}"""\n'


@register(
    RuleMetadata(
        code="DOC001",
        namespace="DOC",
        summary="Function missing a required docstring",
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
    """Check whether a required docstring is present."""
    if doc is not None:
        return []

    tier = int(config.options.get("tier", 2))  # ty: ignore[invalid-argument-type]
    tier_label = f"Tier {tier}"

    stub = _stub_docstring(func, tier)
    fix = Fix(
        description="Insert stub docstring",
        file_path=func.file_path,
        start_offset=func.def_end_offset,
        end_offset=func.def_end_offset,
        replacement=stub,
    )

    return [
        RuleResult(
            code="DOC001",
            severity=config.severity,
            message=f"{tier_label} function missing docstring",
            location=SourceLocation(
                file_path=func.file_path,
                line=func.line,
                column=func.column,
            ),
            fix=fix,
        )
    ]

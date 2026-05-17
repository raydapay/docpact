"""DOC001 — missing docstring on a function that requires one.

Fires when a function's tier requires a docstring (Tier 1 and above —
which is all tiers) and no docstring is present.

The safe fix inserts a stub docstring with [FILL] markers, which
themselves fail DOC099 (placeholder not replaced) and cannot pass the
pipeline unmodified.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring


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
    raise NotImplementedError("DOC001 not yet implemented")

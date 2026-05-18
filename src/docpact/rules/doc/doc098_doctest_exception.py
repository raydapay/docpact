"""DOC098 — Example in docstring raised an exception when run as a doctest.

Fires when --doctest mode is enabled and a docstring Examples section
contains code that raises an exception instead of producing the expected
output. The [FILL] stub marker also triggers this via DOC099 (output
mismatch with any expected output).

Deferred: requires --doctest CLI flag and a live doctest runner. The
current structural-only mode does not execute any code. Implement when
doctest execution is added to the check command.
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
        code="DOC098",
        namespace="DOC",
        summary="Docstring example raised an exception when run as a doctest",
        default_severity=Severity.ERROR,
        fixable=False,
        unsafe_fixable=False,
    )
)
def check(
    func: FunctionInfo,
    doc: ParsedDocstring | None,
    config: RuleConfig,
) -> list[RuleResult]:
    """Check doctest examples — deferred until --doctest mode is implemented."""
    return []  # requires --doctest flag and live code execution

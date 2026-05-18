"""DOC098 — Example in docstring raised an exception when run as a doctest.

Permanently out of scope. Executing docstring Examples sections as doctests
has arbitrary side effects — network calls, file writes, database mutations,
process spawns. There is no safe sandboxing strategy for a structural linter
that does not require reimplementing a full test harness. The code is reserved
so the error code cannot be reused; the check function is permanently empty.

If you need doctest execution, run Python's built-in doctest module directly:

    python -m doctest your_module.py
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
    """DOC098 is permanently out of scope. See module docstring."""
    return []

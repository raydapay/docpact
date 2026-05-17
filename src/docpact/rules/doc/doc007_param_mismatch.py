"""DOC007 — parameter list mismatch between signature and Args section.

Fires when:
- A parameter exists in the function signature but is absent from Args.
- A parameter exists in Args but is absent from the function signature.

The safe fix:
- Adds missing entries with [FILL] markers (subject to DOC099).
- Removes stale entries that no longer correspond to parameters.

It does not attempt to detect rename intent. A parameter that has been
renamed appears as one missing entry and one stale entry; the safe fix
removes the stale entry and adds a stub for the new name. The agent or
human must verify the description applies to the renamed parameter.

DOC014 is a separate rule for the specific case where a typo is
detectable; DOC007 fires for the structural mismatch regardless.
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
        code="DOC007",
        namespace="DOC",
        summary="Parameter list mismatch between signature and Args section",
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
    """Check Args section consistency with the function signature."""
    raise NotImplementedError("DOC007 not yet implemented")

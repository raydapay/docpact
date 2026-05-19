"""DOC021 — "Defaults to X" in Args prose does not match the signature default.

Fires when an Args entry contains a ``Defaults to <value>`` phrase whose
value does not match the parameter's actual default in the function
signature.

Example of a drift that triggers DOC021:
    def fetch(count: int = 5) -> list:
        '''Fetch items.

        Args:
            count: Number of items to fetch. Defaults to 10.
        '''

No auto-fix. The mismatch could mean either the code or the docstring is
wrong; the correct resolution requires human judgement.

Only fires when:
- The parameter has a default in the signature.
- The description contains a ``Defaults to`` phrase.
- The extracted value does not match the signature default.

Does not fire when the parameter has no default (cannot meaningfully
compare) or when no ``Defaults to`` phrase is present.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring

# Matches "Defaults to X" or "defaults to X". Captures X as:
# - A quoted string literal ('...' or "...")
# - OR a run of non-whitespace, non-comma, non-semicolon characters with
#   embedded decimal points allowed (e.g. 3.14, [], {}, True, None, 'x').
_DEFAULTS_TO_RE: re.Pattern[str] = re.compile(
    r'\bdefaults?\s+to\s+(["\'][^"\']*["\']|[^\s,;.\n]+(?:\.[^\s,;.\n]+)*)',
    re.IGNORECASE,
)


def _normalize(s: str) -> str:
    """Strip whitespace and remove one layer of matching quotes for comparison."""
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    return s


@register(
    RuleMetadata(
        code="DOC021",
        namespace="DOC",
        summary='"Defaults to X" in Args prose does not match the signature default',
        default_severity=Severity.WARNING,
        fixable=False,
        unsafe_fixable=False,
    )
)
def check(
    func: FunctionInfo,
    doc: ParsedDocstring | None,
    config: RuleConfig,
) -> list[RuleResult]:
    """Check that 'Defaults to X' phrases match the actual signature default."""
    if doc is None:
        return []

    args_section = doc.sections.get("Args")
    if args_section is None or not args_section.entries:
        return []

    param_defaults: dict[str, str] = {
        p.name: p.default for p in func.parameters if p.kind != "bound" and p.default is not None
    }

    results: list[RuleResult] = []
    loc = SourceLocation(file_path=func.file_path, line=func.line, column=func.column)

    for entry in args_section.entries:
        name = entry.key.lstrip("*")
        if name not in param_defaults:
            continue
        m = _DEFAULTS_TO_RE.search(entry.description)
        if m is None:
            continue
        documented = _normalize(m.group(1))
        actual = _normalize(param_defaults[name])
        if documented != actual:
            results.append(
                RuleResult(
                    code="DOC021",
                    severity=config.severity,
                    message=(
                        f"Parameter {name!r}: docstring says 'Defaults to {m.group(1)}' "
                        f"but signature default is {param_defaults[name]!r}"
                    ),
                    location=loc,
                )
            )

    return results

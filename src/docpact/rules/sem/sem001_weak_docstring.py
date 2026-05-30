"""SEM001 — docstring is semantically weak or empty (LLM-judged).

Fires when a docstring adds nothing beyond the signature (cargo-cult
restatement), implies a precondition/constraint/side-effect it does not
surface (hidden contract), or has a Returns that only restates the return type.

This is the meaning-level check that the deterministic `check` rules cannot do
and that DOC051/REG050 were declined for (a heuristic false-positives). It is
produced by `docpact semantic` via an LLM, is **non-deterministic and advisory**,
and never runs inside `check` — so `check`'s reproducibility is untouched.
See ADR-008 and docpact.semantic.analyzer.

This module registers the SEM001 metadata so it appears in `list-rules` and the
generated docs; the registered check is a no-op stub, because the real analysis
is batched and LLM-backed (it cannot fit the per-function rule signature). SEM is
not in the default `select`.
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
        code="SEM001",
        namespace="SEM",
        summary="Docstring is semantically weak/empty (advisory; `docpact semantic`)",
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
    """SEM001 is produced by `docpact semantic`, not `check`; this stub is a no-op."""
    return []

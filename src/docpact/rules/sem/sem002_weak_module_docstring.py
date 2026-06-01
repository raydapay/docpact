"""SEM002 — module docstring is semantically weak (LLM-judged; ADR-013).

Fires when a module docstring is out of scope with the module's public symbols
(describes a purpose the symbols do not support, or names a symbol that does not
exist) or is pure boilerplate ("Utilities.", "The widgets module."). It is the
module-level companion to SEM001: DOC002 guarantees a module docstring *exists*;
SEM002 judges whether it is *useful*.

Produced by `docpact semantic` (scan mode "module") via an LLM — **non-deterministic
and advisory**, never inside `check`. Opt in with `scan_modes = ["module"]`.

**Model-sensitive (ADR-013): reliable only on a gpt-4o-class model.** On weak
models (e.g. gpt-4o-mini) it produced 43-71% false positives by demanding symbol
enumeration; on gpt-4o, 0%. Do not run module scan without a capable model.

This module registers the SEM002 metadata so it appears in `list-rules` and the
generated docs; the registered check is a no-op stub — the real analysis is
batched and LLM-backed (docpact.semantic.analyzer.analyze_modules).
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
        code="SEM002",
        namespace="SEM",
        summary="Module docstring is semantically weak (advisory; module scan)",
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
    """SEM002 is produced by `docpact semantic` (module scan), not `check`; no-op stub."""
    return []

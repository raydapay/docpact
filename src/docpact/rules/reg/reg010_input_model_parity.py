"""REG010 — tool Args section out of parity with its imported input model.

Cross-file rule (ADR-009). A tool-registration entry that names an imported
Pydantic model as its ``input_model`` and documents parameters in its
description's ``Args:`` section asserts two things that must agree: the
documented args and the model's actual fields. REG010 fires when they drift —
a model field the Args don't document, or an Args entry with no matching field.

This is the cross-file analogue of REG001's same-file phantom-parameter check.
It runs only under ``docpact check --crossfile`` (opt-in) and only when a
language server resolves the model's defining file (ADR-009); the registered
``check`` function below is an inert stub that keeps REG010 in ``list-rules``.
The resolution + AST extraction live in ``docpact.crossfile``; the pure
comparison is ``parity_findings`` here.

Direction matters for the message but not the verdict: both a missing-in-doc
and a missing-in-model discrepancy are real drift and each emits one finding.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from pathlib import Path

    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring
    from docpact.model.tool_registry import ToolRegistryEntry


@register(
    RuleMetadata(
        code="REG010",
        namespace="REG",
        summary="Tool Args section out of parity with its imported input model",
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
    """REG010 is a cross-file pass; all parameters unused. See parity_findings."""
    return []


def parity_findings(
    entry: ToolRegistryEntry,
    file_path: Path,
    model_fields: frozenset[str],
    severity: Severity,
) -> list[RuleResult]:
    """Compare an entry's documented Args to its model's fields and emit drift.

    Args:
        entry: The registry entry. Its ``description_arg_keys`` (the documented
            Args) and ``input_model_ref`` (the model symbol) must both be set —
            the cross-file pass only calls this for such entries.
        file_path: The file the entry appears in, for the diagnostic location.
        model_fields: Field names of the resolved input model.
        severity: Resolved severity for REG010.

    Returns:
        One RuleResult per discrepancy, located at the entry: a model field
        absent from the Args, then an Args key absent from the model, each
        sorted by name. Empty when the documented Args and model fields match.
    """
    doc_keys = entry.description_arg_keys or frozenset()
    model_name = entry.input_model_ref.name if entry.input_model_ref else "the input model"
    location = SourceLocation(file_path=file_path, line=entry.line, column=entry.column)

    results: list[RuleResult] = []
    for field in sorted(model_fields - doc_keys):
        results.append(
            RuleResult(
                code="REG010",
                severity=severity,
                message=(
                    f"input model '{model_name}' field '{field}' is not documented "
                    f"in tool '{entry.name}' Args section"
                ),
                location=location,
            )
        )
    for key in sorted(doc_keys - model_fields):
        results.append(
            RuleResult(
                code="REG010",
                severity=severity,
                message=(
                    f"tool '{entry.name}' Args entry '{key}' has no matching field "
                    f"in input model '{model_name}'"
                ),
                location=location,
            )
        )
    return results

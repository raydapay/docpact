"""REG011 — tool declares a parameter its imported handler does not accept.

The cross-file analogue of REG001 (ADR-010 FR-2(b)). REG001 flags a same-file
schema property absent from the registered function's signature; REG011 does the
same when the handler is *imported* from another module: the handler is resolved
via the LSP server, its signature is read by AST, and the entry's declared
parameters are checked against it.

"Declared parameters" come from the JSON-schema ``properties`` keys when present,
otherwise from the imported ``input_model``'s fields. Two guards keep this
low-false-positive, in the spirit of REG001/REG005's literals-only discipline:

- If the handler takes the input model as a single typed parameter
  (``def handler(payload: SearchInput)``) rather than unpacked fields, the
  model-field comparison is skipped — the handler validly receives the whole model.
- If the handler accepts ``**kwargs``, nothing is phantom — it accepts any key.

Like REG001 this is phantom-direction only (declared-but-not-accepted); a
signature parameter absent from the schema is legitimate non-exposure (REG003,
reserved). It runs only under ``docpact check --crossfile``; the registered check
function is an inert stub that keeps REG011 in ``list-rules``. The resolution and
AST extraction live in ``docpact.crossfile``; the pure comparison is here.
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
        code="REG011",
        namespace="REG",
        summary="Tool declares a parameter its imported handler does not accept",
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
    """REG011 is a cross-file pass; all parameters unused. See signature_findings."""
    return []


def _takes_model_instance(handler: FunctionInfo, model_name: str) -> bool:
    """Return True if the handler takes the model as a single typed parameter.

    Args:
        handler: The resolved handler function.
        model_name: The input-model symbol name.

    Returns:
        True when the handler has exactly one non-receiver parameter whose
        annotation references the model — the "receives the whole model" shape,
        for which a field-by-field signature comparison does not apply.
    """
    params = [p for p in handler.parameters if p.kind != "bound"]
    if len(params) != 1:
        return False
    return model_name in (params[0].annotation or "")


def _declared_params(
    entry: ToolRegistryEntry, handler: FunctionInfo, model_fields: frozenset[str] | None
) -> tuple[frozenset[str] | None, str]:
    """Return the entry's declared parameter set and its source label, or (None, "").

    Prefers the JSON-schema ``properties`` keys; falls back to the imported
    model's fields unless the handler takes the model instance. Returns None
    when no comparable declaration exists.
    """
    if entry.property_keys is not None:
        return entry.property_keys, "schema"
    if model_fields is not None and entry.input_model_ref is not None:
        if _takes_model_instance(handler, entry.input_model_ref.name):
            return None, ""
        return model_fields, "input model"
    return None, ""


def signature_findings(
    entry: ToolRegistryEntry,
    file_path: Path,
    handler: FunctionInfo,
    model_fields: frozenset[str] | None,
    severity: Severity,
) -> list[RuleResult]:
    """Emit REG011 for each declared parameter the imported handler does not accept.

    Args:
        entry: The registry entry (its ``handler_ref`` must be set — the
            cross-file pass only calls this for resolved imported handlers).
        file_path: The file the entry appears in, for the diagnostic location.
        handler: The resolved handler's FunctionInfo (from its defining file).
        model_fields: The imported model's fields, or None when there is no
            input model or it did not resolve.
        severity: Resolved severity for REG011.

    Returns:
        One RuleResult per phantom declared parameter, located at the entry,
        sorted by name. Empty when the handler accepts ``**kwargs``, takes the
        model instance, or there is no comparable declaration.
    """
    if any(p.kind == "var_keyword" for p in handler.parameters):
        return []  # accepts arbitrary keys — nothing is phantom
    declared, source = _declared_params(entry, handler, model_fields)
    if declared is None:
        return []
    handler_params = frozenset(p.name for p in handler.parameters if p.kind != "bound")
    handler_name = entry.handler_ref.name if entry.handler_ref else "the handler"
    location = SourceLocation(file_path=file_path, line=entry.line, column=entry.column)
    return [
        RuleResult(
            code="REG011",
            severity=severity,
            message=(
                f"tool {entry.name!r} {source} declares parameter {param!r}, which "
                f"imported handler {handler_name!r} does not accept"
            ),
            location=location,
        )
        for param in sorted(declared - handler_params)
    ]

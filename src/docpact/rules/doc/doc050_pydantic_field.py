"""DOC050 — Pydantic model field missing Field(description=...).

Fires when a class that inherits from BaseModel has an annotated field
without a ``Field(description=...)`` call. Field-level documentation belongs
in ``Field(description=...)`` rather than in the caller's ``Args`` section:
the model travels independently and its contract should be self-contained.

Detection heuristic:
- A class is treated as a Pydantic model if any of its direct base class
  names contains ``"BaseModel"`` (covers ``BaseModel``, ``pydantic.BaseModel``,
  ``pydantic.v1.BaseModel``, custom sub-bases named ``*BaseModel``).
- A field is an annotated class-body variable (``ast.AnnAssign``) whose
  name does not start with ``_`` and whose annotation is not ``ClassVar[...]``.
- A field is documented when its default value is a ``Field(...)`` call
  with a non-empty ``description=`` keyword argument.

The heuristic errs on the side of false negatives (misses exotic base names)
rather than false positives (noisy on non-Pydantic classes).

This is a file-level rule. The CLI's source scan calls check_pydantic_fields
directly; the registered check function is a no-op stub that keeps DOC050
visible in list-rules.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.parser.pydantic_model import is_pydantic_model, iter_model_fields
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from pathlib import Path

    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring


@register(
    RuleMetadata(
        code="DOC050",
        namespace="DOC",
        summary="Pydantic model field missing Field(description=...)",
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
    """DOC050 is file-level; all parameters unused. See check_pydantic_fields."""
    return []


def _has_field_description(value: ast.expr | None) -> bool:
    """Return True if value is a Field(...) call with a non-empty description=."""
    if not isinstance(value, ast.Call):
        return False
    func_name = ast.unparse(value.func)
    if func_name != "Field" and not func_name.endswith(".Field"):
        return False
    for kw in value.keywords:
        if kw.arg == "description":
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value.strip() != ""
            return True  # variable/computed description — accept
    return False


def check_pydantic_fields(
    source: str,
    file_path: Path,
    config: RuleConfig,
) -> list[RuleResult]:
    """Emit DOC050 for each Pydantic model field missing Field(description=...).

    Args:
        source: Full source text of the file.
        file_path: Path to the source file (for SourceLocation).
        config: Rule configuration including severity.

    Returns:
        One RuleResult per undocumented field, in source order. Classes that
        don't look like Pydantic models are skipped. Files that fail to parse
        are silently skipped.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    results: list[RuleResult] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not is_pydantic_model(node):
            continue
        for name, stmt in iter_model_fields(node):
            if _has_field_description(stmt.value):
                continue
            results.append(
                RuleResult(
                    code="DOC050",
                    severity=config.severity,
                    message=(
                        f"Pydantic field '{name}' has no Field(description=...); "
                        "field contracts belong in the type, not the caller's Args"
                    ),
                    location=SourceLocation(
                        file_path=file_path,
                        line=stmt.lineno,
                        column=stmt.col_offset,
                    ),
                )
            )

    results.sort(key=lambda r: (r.location.line, r.location.column))
    return results

"""DOC022 — Typed prose annotation doesn't match signature type.

Fires *only* when an Args entry contains an explicit inline type annotation —
the ``name(type): description`` form — and that type doesn't match the
parameter's annotation in the signature. Entries without an inline type
(``name: description``) are ignored entirely.

## What this catches

The author made an explicit type claim in prose. The rule verifies the claim
is internally consistent with the signature:

    def foo(x: float) -> None:
        '''
        Args:
            x (int): description   ← fires: prose says int, signature says float
        '''

    def bar(x: str) -> None:
        '''
        Args:
            x (str | None): description   ← fires: prose says optional, signature isn't
        '''

This is the same design principle as DOC021: the rule only activates when
the author chose to write something checkable. If they wrote a type in
prose, they're making a claim. The tool verifies the claim.

## When the rule is silent

- The entry has no inline type: ``x: description`` (the common modern form).
  This is the majority of well-annotated Python code. The rule ignores it.
- The parameter has no annotation in the signature (unannotated). No basis
  for comparison.
- ``self`` / ``cls`` and other bound parameters.
- The function has no docstring.

## Known false positives — notation differences that DO fire

Type normalization is deliberately minimal: only leading/trailing whitespace
is stripped. No semantic type equivalence is attempted. The following
combinations produce a DOC022 warning even though the types are semantically
identical:

- ``Optional[str]`` (prose) vs ``str | None`` (signature) — pre-PEP 604
  vs modern union notation.
- ``List[int]`` (prose) vs ``list[int]`` (signature) — pre-PEP 585 vs
  modern generic notation.
- ``Union[A, B]`` (prose) vs ``A | B`` (signature) — pre/post PEP 604.
- Forward references: ``"Foo"`` (stringified annotation) vs ``Foo`` (bare
  name).

These fire because the strings differ, even though the types are equivalent.
The tradeoff is accepted deliberately: implementing type normalization would
require AST-level type resolution and special-case logic for every
``typing.*`` alias, adding complexity that is hard to test exhaustively and
prone to new edge cases with each Python release.

In practice, code that writes inline types in docstrings tends to use one
consistent notation style, so these cross-style false positives are rare.
If DOC022 fires on a notation difference, suppress with
``# nodo: DOC022 -- notation style difference, types are equivalent``.

The rule's primary target is the obvious post-refactoring drift case:
prose says ``int``, signature says ``float``. That is reliably caught with
no normalization at all.

## Implementation note on type comparison

Both the prose type (from the docstring) and the signature type (from the
AST) are compared as raw strings after whitespace normalization. The prose
type is whatever the docstring parser extracted from the parentheses; the
signature type is whatever ``ast.unparse`` produced from the annotation
node. If either side cannot be compared (None, empty string), the entry is
silently skipped.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring


@register(
    RuleMetadata(
        code="DOC022",
        namespace="DOC",
        summary="Typed prose annotation doesn't match signature type",
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
    """Check inline prose types against the signature annotation.

    Args:
        func: Parsed function information including parameter annotations.
        doc: Parsed docstring, or None if absent.
        config: Rule configuration including effective severity.

    Returns:
        One DOC022 diagnostic per Args entry where the inline prose type
        does not match the parameter's signature annotation. Empty when
        there are no inline types, no annotations, or all types match.
    """
    if doc is None:
        return []
    args_section = doc.sections.get("Args")
    if args_section is None or not args_section.entries:
        return []

    sig_annotations: dict[str, str] = {
        p.name: p.annotation
        for p in func.parameters
        if p.kind != "bound" and p.annotation is not None
    }

    results: list[RuleResult] = []
    loc = SourceLocation(file_path=func.file_path, line=func.line, column=func.column)

    for entry in args_section.entries:
        if entry.type_annotation is None:
            continue
        prose_type = entry.type_annotation.strip()
        if not prose_type:
            continue
        sig_type = sig_annotations.get(entry.key)
        if sig_type is None:
            continue
        sig_type = sig_type.strip()
        if prose_type == sig_type:
            continue
        results.append(
            RuleResult(
                code="DOC022",
                severity=config.severity,
                message=(
                    f"Parameter {entry.key!r} annotated as {prose_type!r} in docstring"
                    f" but {sig_type!r} in signature"
                ),
                location=loc,
            )
        )

    return results

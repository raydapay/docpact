"""DOC003 — Missing docstring on a class definition.

Fires when a class body does not begin with a string literal. Applies to
class definitions that are considered part of the module's public API.

## Tier logic applied to classes

DOC003 respects the same visibility conventions as the function-level rules:

- **Leading underscore → silent.** Classes named ``_Helper``, ``_Cache``,
  etc. are assumed private and never fire DOC003.

- **Module defines ``__all__`` → only listed classes fire.** When a module
  provides an explicit export list, any class absent from it is treated as
  internal infrastructure. DOC003 will not fire for those classes.

  *Note:* ``__all__`` is only meaningful for top-level (module-level)
  classes. Nested classes are not affected by ``__all__``.

- **No ``__all__``, no leading underscore → fires.** Without an explicit
  contract, a public-looking name is assumed to be part of the API.

**Consequence for internal Pydantic / dataclass structs:** define
``__all__`` in the module listing your truly public exports, or prefix
internal structs with ``_``. Either convention suppresses DOC003 for the
unlisted classes with no per-file-ignores needed.

## File-level ignores

Disable for specific files (generated code, stubs, migration scripts) via
per-file-ignores:

    [tool.docpact.per-file-ignores]
    "src/generated/**/*.py" = ["DOC003"]

Or suppress inline on the ``class`` keyword line:

    class LegacyHelper(  # nodo: DOC003 -- grandfathered, refactor tracked in #99
        Base,
    ):

This is a file-level rule. The CLI's source scan calls check_class_docstrings
directly; the registered check function is a no-op stub that keeps DOC003
visible in list-rules.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from pathlib import Path

    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring


@register(
    RuleMetadata(
        code="DOC003",
        namespace="DOC",
        summary="Missing docstring on a class definition",
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
    """DOC003 is file-level; all parameters unused. See check_class_docstrings."""
    return []


def _parse_all_names(tree: ast.Module) -> frozenset[str] | None:
    """Return names from a module-level ``__all__`` list/tuple, or None."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (isinstance(target, ast.Name) and target.id == "__all__"):
                continue
            val = node.value
            if not isinstance(val, (ast.List, ast.Tuple)):
                return None
            names: set[str] = set()
            for elt in val.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    names.add(elt.value)
                else:
                    return None
            return frozenset(names)
    return None


def check_class_docstrings(
    source: str,
    file_path: Path,
    config: RuleConfig,
) -> list[RuleResult]:
    """Emit DOC003 for each class in the file that has no docstring.

    Visibility rules applied before checking (see module docstring):
    - Classes with a leading underscore are skipped.
    - When the module defines ``__all__``, top-level classes not listed
      in it are skipped.

    Args:
        source: Full source text of the file.
        file_path: Path to the source file (for SourceLocation).
        config: Rule configuration including severity.

    Returns:
        One RuleResult per undocumented visible class, in source order.
        Files that fail to parse are silently skipped.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    all_names = _parse_all_names(tree)

    # Top-level class names — __all__ only governs module-level exports.
    top_level_class_names: frozenset[str] = frozenset(
        node.name for node in tree.body if isinstance(node, ast.ClassDef)
    )

    results: list[RuleResult] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name.startswith("_"):
            continue
        # __all__ is only meaningful for top-level names; don't filter nested classes.
        if (
            all_names is not None
            and node.name in top_level_class_names
            and node.name not in all_names
        ):
            continue
        has_docstring = (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        )
        if not has_docstring:
            results.append(
                RuleResult(
                    code="DOC003",
                    severity=config.severity,
                    message=f"Class '{node.name}' has no docstring",
                    location=SourceLocation(
                        file_path=file_path,
                        line=node.lineno,
                        column=node.col_offset,
                    ),
                )
            )

    results.sort(key=lambda r: (r.location.line, r.location.column))
    return results

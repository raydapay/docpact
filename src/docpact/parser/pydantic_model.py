"""Pydantic model detection and field enumeration via stdlib ast.

The single source of truth for "is this a Pydantic model?" and "what are its
field names?". DOC050 uses these predicates to flag undocumented fields; the
cross-file parity pass (ADR-009) uses ``model_field_names`` to read a resolved
model's fields and compare them to a tool's documented Args.

Static only: no import, no execution. The detection heuristic errs toward false
negatives (an exotic base name is missed) over false positives (noise on
non-models), matching DOC050's long-standing behaviour.
"""

from __future__ import annotations

import ast


def is_pydantic_model(node: ast.ClassDef) -> bool:
    """Return True if the class appears to inherit from BaseModel.

    Args:
        node: A class definition node.

    Returns:
        True when any direct base's source contains ``"BaseModel"`` — covers
        ``BaseModel``, ``pydantic.BaseModel``, ``pydantic.v1.BaseModel``, and
        custom ``*BaseModel`` sub-bases.
    """
    return any("BaseModel" in ast.unparse(base) for base in node.bases)


def is_classvar(annotation: ast.expr) -> bool:
    """Return True if the annotation looks like ClassVar[...].

    Args:
        annotation: The annotation expression of a class-body assignment.

    Returns:
        True for ``ClassVar`` or ``ClassVar[...]`` — declarations that are not
        model fields and must be excluded.
    """
    text = ast.unparse(annotation)
    return text.startswith("ClassVar[") or text == "ClassVar"


def iter_model_fields(node: ast.ClassDef) -> list[tuple[str, ast.AnnAssign]]:
    """Return the model fields of a class as (name, statement) pairs.

    Args:
        node: A class definition node (assumed to be a Pydantic model).

    Returns:
        One ``(name, AnnAssign)`` pair per ``name: T`` class-body statement
        whose name is not private (no leading underscore) and whose annotation
        is not ``ClassVar[...]``, in source order. The statement is retained so
        callers needing a source position (DOC050) have it.
    """
    fields: list[tuple[str, ast.AnnAssign]] = []
    for stmt in node.body:
        if not isinstance(stmt, ast.AnnAssign):
            continue
        if not isinstance(stmt.target, ast.Name):
            continue
        if stmt.target.id.startswith("_"):
            continue
        if is_classvar(stmt.annotation):
            continue
        fields.append((stmt.target.id, stmt))
    return fields


def model_field_names(source: str, class_name: str) -> frozenset[str] | None:
    """Return the field names of a named Pydantic model in source, or None.

    Args:
        source: Raw Python source text of the file defining the model.
        class_name: The model class to look for.

    Returns:
        The model's field names as a frozenset. None when the source cannot be
        parsed, no class of that name is found, or the matching class does not
        look like a Pydantic model — in every "None" case the parity check is
        skipped rather than guessed.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            if not is_pydantic_model(node):
                return None
            return frozenset(name for name, _ in iter_model_fields(node))
    return None

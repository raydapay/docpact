"""Extract FunctionInfo from Python source files via stdlib ast.

This module is intentionally minimal — it walks the AST once per file,
collects function and class definitions, extracts signatures and
decorators, and locates the raw docstring text. It does not interpret,
validate, or analyze beyond that.

Why stdlib ast and not griffe for this step:
    griffe builds a richer object model than docpact needs and walks the
    same files we already need to walk. Using ast.parse directly is
    ~2-3x faster for our needs and gives us full control over how
    FunctionInfo is constructed.

Why not tree-sitter:
    See ADR-001. Python is the v0.1 implementation language, and the
    stdlib ast module is the obvious choice within Python.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from docpact.model.function_info import DecoratorInfo, FunctionInfo, ParameterInfo

if TYPE_CHECKING:
    from pathlib import Path


def extract_functions(source_path: Path) -> list[FunctionInfo]:
    """Extract all function and method definitions from a source file.

    Args:
        source_path: Path to a .py file.

    Returns:
        FunctionInfo for every function and method definition in the file,
        in source order. Module-level functions, class methods, nested
        functions, and async functions are all included.

    Raises:
        SyntaxError: source_path contains invalid Python.
        OSError: source_path cannot be read.

    Constraints:
        Operates on a single file. Does not follow imports. Does not
        evaluate any code.

    Stability: beta
    """
    source_bytes = source_path.read_bytes()
    source_text = source_bytes.decode("utf-8")
    tree = ast.parse(source_text, filename=str(source_path))
    line_offsets = _build_line_offsets(source_bytes)
    visitor = _FunctionVisitor(source_path, source_bytes, line_offsets)
    visitor.visit(tree)
    return visitor.functions


def _extract_docstring_raw(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Return the raw docstring text for a function node, or None.

    The returned text is the string literal value as stored in the AST —
    no dedenting or cleaning applied. The caller is responsible for
    normalizing whitespace before parsing.
    """
    if (
        node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    ):
        return node.body[0].value.value
    return None


def _build_line_offsets(source_bytes: bytes) -> list[int]:
    """Return byte offset of the first byte of each line.

    The returned list is 0-indexed: offsets[0] is the byte offset of
    line 1, offsets[1] is line 2, etc.
    """
    offsets: list[int] = [0]
    for i, byte in enumerate(source_bytes):
        if byte == 0x0A:  # newline
            offsets.append(i + 1)
    return offsets


def _char_to_byte_offset(
    line_offsets: list[int],
    lineno: int,
    col_chars: int,
    source_bytes: bytes,
) -> int:
    """Convert line number (1-based) and character column to byte offset.

    ast.col_offset is a character (Unicode code point) offset within the
    line, not a byte offset. For non-ASCII source they diverge. This
    function converts to the byte offset Fix objects require.
    """
    line_start = line_offsets[lineno - 1]
    next_line = line_offsets[lineno] if lineno < len(line_offsets) else len(source_bytes)
    line_text = source_bytes[line_start:next_line].decode("utf-8", errors="replace")
    byte_col = len(line_text[:col_chars].encode("utf-8"))
    return line_start + byte_col


def _decorator_name(node: ast.expr) -> str:
    """Extract the name of a decorator as a dotted string."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_decorator_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ast.unparse(node)


def _decorator_kwargs(node: ast.expr) -> dict[str, str]:
    """Extract keyword arguments from a decorator call as source text."""
    if not isinstance(node, ast.Call):
        return {}
    return {kw.arg: ast.unparse(kw.value) for kw in node.keywords if kw.arg is not None}


class _FunctionVisitor(ast.NodeVisitor):
    """AST visitor that collects FunctionInfo for every function definition."""

    def __init__(
        self,
        source_path: Path,
        source_bytes: bytes,
        line_offsets: list[int],
    ) -> None:
        """Set up the visitor with the source file and its precomputed line-offset table."""
        self.source_path = source_path
        self.source_bytes = source_bytes
        self.line_offsets = line_offsets
        self.functions: list[FunctionInfo] = []
        # Stack of scope markers: a str means we just entered a ClassDef with
        # that name; None means we just entered a FunctionDef. A function is a
        # method only if the innermost scope on the stack is a class name.
        self._scope_stack: list[str | None] = []

    @property
    def _containing_class(self) -> str | None:
        """Innermost class name, or None if inside a function or at module level."""
        for scope in reversed(self._scope_stack):
            if scope is None:
                return None
            return scope
        return None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Push the class name onto the scope stack, visit body, then pop."""
        self._scope_stack.append(node.name)
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Collect the function, then visit its body with None on the scope stack."""
        self._collect(node)
        self._scope_stack.append(None)
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Collect the async function, then visit its body with None on the scope stack."""
        self._collect(node)
        self._scope_stack.append(None)
        self.generic_visit(node)
        self._scope_stack.pop()

    def _collect(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Extract a FunctionInfo from an AST function node and append it to self.functions."""
        containing_class = self._containing_class
        is_static = any(_decorator_name(d) == "staticmethod" for d in node.decorator_list)
        parameters = _extract_parameters(node, containing_class, is_static)
        decorators = [
            DecoratorInfo(
                name=_decorator_name(d),
                arguments=_decorator_kwargs(d),
            )
            for d in node.decorator_list
        ]
        raw_doc = _extract_docstring_raw(node)
        doc_line = node.lineno

        # Byte offsets for the function definition and docstring.
        def_start = _char_to_byte_offset(
            self.line_offsets, node.lineno, node.col_offset, self.source_bytes
        )
        # def_end: start of the first line of the function body (after the
        # colon that closes the def), suitable for inserting a docstring stub.
        first_body_lineno = node.body[0].lineno
        def_end = self.line_offsets[first_body_lineno - 1]

        doc_start: int | None = None
        doc_end: int | None = None
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            doc_node = node.body[0].value
            doc_line = doc_node.lineno
            doc_start = _char_to_byte_offset(
                self.line_offsets, doc_node.lineno, doc_node.col_offset, self.source_bytes
            )
            # end_lineno and end_col_offset are always set on ast.Constant (3.8+)
            assert doc_node.end_lineno is not None
            assert doc_node.end_col_offset is not None
            doc_end = _char_to_byte_offset(
                self.line_offsets,
                doc_node.end_lineno,
                doc_node.end_col_offset,
                self.source_bytes,
            )

        return_annotation: str | None = None
        if node.returns is not None:
            return_annotation = ast.unparse(node.returns)

        self.functions.append(
            FunctionInfo(
                name=node.name,
                file_path=self.source_path,
                line=node.lineno,
                column=node.col_offset,
                parameters=tuple(parameters),
                return_annotation=return_annotation,
                decorators=tuple(decorators),
                docstring_raw=raw_doc,
                docstring_line=doc_line,
                containing_class=containing_class,
                def_start_offset=def_start,
                def_end_offset=def_end,
                docstring_start_offset=doc_start,
                docstring_end_offset=doc_end,
            )
        )


def _extract_parameters(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    containing_class: str | None,
    is_static: bool,
) -> list[ParameterInfo]:
    """Build the ordered ParameterInfo list from an AST function node.

    The first positional parameter of a non-static method gets kind="bound"
    regardless of its name. All other parameters follow their syntactic
    position in the signature.
    """
    args = node.args
    params: list[ParameterInfo] = []
    is_method = containing_class is not None and not is_static

    # Positional-only (before /) and regular positional/keyword args share
    # a single defaults list that is right-aligned. If there are N positional
    # params total and D defaults, defaults[i] maps to positional param
    # N-D+i (0-indexed).
    all_pos = list(args.posonlyargs) + list(args.args)
    n_pos = len(all_pos)
    n_defaults = len(args.defaults)

    for idx, arg in enumerate(all_pos):
        default_list_idx = idx - (n_pos - n_defaults)
        default: str | None = (
            ast.unparse(args.defaults[default_list_idx]) if default_list_idx >= 0 else None
        )
        annotation: str | None = ast.unparse(arg.annotation) if arg.annotation else None
        kind = "bound" if is_method and idx == 0 else "positional"
        params.append(
            ParameterInfo(name=arg.arg, annotation=annotation, default=default, kind=kind)
        )

    if args.vararg:
        params.append(
            ParameterInfo(
                name=args.vararg.arg,
                annotation=ast.unparse(args.vararg.annotation) if args.vararg.annotation else None,
                default=None,
                kind="var_positional",
            )
        )

    for i, arg in enumerate(args.kwonlyargs):
        kw_default = args.kw_defaults[i]
        params.append(
            ParameterInfo(
                name=arg.arg,
                annotation=ast.unparse(arg.annotation) if arg.annotation else None,
                default=ast.unparse(kw_default) if kw_default is not None else None,
                kind="keyword",
            )
        )

    if args.kwarg:
        params.append(
            ParameterInfo(
                name=args.kwarg.arg,
                annotation=ast.unparse(args.kwarg.annotation) if args.kwarg.annotation else None,
                default=None,
                kind="var_keyword",
            )
        )

    return params

"""Resolve imported input models via LSP and check Args parity (REG010).

The cross-file pass for ADR-009. It collects the tool-registry entries that
both name an importable ``input_model`` (a bare ``Name``) and document an
``Args:`` section, spins up one LSP client for the run, resolves each model to
its defining file with ``textDocument/definition``, reads that model's fields
by static AST extraction, and emits REG010 for any drift.

One client serves the whole run; resolved files are cached by (path, model
name) so a model referenced by several tools is read once. A reference that the
server cannot resolve, or that resolves to a non-Pydantic / missing class, is
skipped rather than reported — cross-file findings are only as confident as the
resolution behind them.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlparse

from docpact.lsp import LSPClient
from docpact.parser.docstring import GoogleParser, NumpyParser
from docpact.parser.pydantic_model import model_field_names
from docpact.parser.registry import extract_tool_registry
from docpact.rules.reg.reg010_input_model_parity import parity_findings

if TYPE_CHECKING:
    from docpact.config import Config
    from docpact.model.diagnostic import RuleResult, Severity
    from docpact.model.tool_registry import ToolRegistryEntry


def _uri_to_path(uri: str) -> Path | None:
    """Convert a ``file://`` URI to a local path, or None for other schemes."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path))


def _collect_entries(py_files: list[Path], config: Config) -> list[tuple[Path, ToolRegistryEntry]]:
    """Collect (file, entry) pairs that are candidates for the parity check.

    Only entries with both a resolvable ``input_model_ref`` and a parsed
    ``description_arg_keys`` qualify — the two facts the comparison needs.
    """
    parser = NumpyParser() if config.docstring_format == "numpy" else GoogleParser()
    pending: list[tuple[Path, ToolRegistryEntry]] = []
    for file_path in py_files:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        entries = extract_tool_registry(
            source,
            tool_classes=config.registry.tool_definition_class,
            name_field=config.registry.name_field,
            description_field=config.registry.description_field,
            parameters_field=config.registry.parameters_field,
            input_model_field=config.registry.input_model_field,
            description_parser=parser,
        )
        for entry in entries:
            if entry.input_model_ref is not None and entry.description_arg_keys is not None:
                pending.append((file_path, entry))
    return pending


def check_input_model_parity(
    py_files: list[Path],
    config: Config,
    root: Path,
    severity: Severity,
) -> list[RuleResult]:
    """Resolve each entry's input model via LSP and emit REG010 parity findings.

    Args:
        py_files: The files in scope for this run.
        config: Resolved configuration (``registry`` field names and ``lsp``
            server/timeout drive extraction and resolution).
        root: Project root, sent to the server as the workspace folder so it
            indexes (and can resolve definitions across) the whole project.
        severity: Resolved severity for REG010.

    Returns:
        REG010 results across all files, sorted by location. Empty when no
        candidate entries exist or none resolve to a Pydantic model.

    Raises:
        LSPError: The language server could not be started or failed during
            the run. The caller reports it as graceful degradation.

    Stability: beta
    """
    pending = _collect_entries(py_files, config)
    if not pending:
        return []

    results: list[RuleResult] = []
    field_cache: dict[tuple[Path, str], frozenset[str] | None] = {}

    with LSPClient(config.lsp.server, root, timeout=config.lsp.timeout) as client:
        for query_file in sorted({f for f, _ in pending}):
            client.did_open(query_file)
        for file_path, entry in pending:
            ref = entry.input_model_ref
            assert ref is not None  # guaranteed by _collect_entries
            # ModelRef.line is 1-based (docpact convention); LSP wants 0-based.
            locations = client.definition(file_path, ref.line - 1, ref.column)
            if not locations:
                continue  # unresolved — skip rather than guess
            target = _uri_to_path(locations[0].uri)
            if target is None:
                continue
            key = (target, ref.name)
            if key not in field_cache:
                field_cache[key] = _read_model_fields(target, ref.name)
            model_fields = field_cache[key]
            if model_fields is None:
                continue  # not a resolvable Pydantic model — skip
            results.extend(parity_findings(entry, file_path, model_fields, severity))

    results.sort(key=lambda r: (str(r.location.file_path), r.location.line, r.location.column))
    return results


def _read_model_fields(target: Path, class_name: str) -> frozenset[str] | None:
    """Read a resolved model's field names, or None if unreadable/not a model."""
    try:
        source = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return model_field_names(source, class_name)

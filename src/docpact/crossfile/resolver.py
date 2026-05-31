"""Resolve imported symbols via LSP for the cross-file pass (ADR-009/ADR-010).

One LSP session does all cross-file work for a run and returns a `CrossfileResult`
with three products, per ADR-010's "one resolution, two consumers":

- **findings** — REG010 Args↔input_model parity (the deterministic FR-1 rule).
- **floor** — the set of `(resolved-file, function-name)` an imported handler is
  registered under, so per-file tier assignment can hold it to the Tier-3 bar.
- **context** — a per-handler note (its tool name, the imported model's fields,
  the registry description) for enriching the semantic prompt.

`check` consumes findings + floor; `semantic` consumes floor + context. Both go
through the same resolution. A reference the server cannot resolve is skipped
(under-enforce), and a missing/failing server raises `LSPError` for the caller to
report as graceful degradation.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    from docpact.model.tool_registry import ModelRef, ToolRegistryEntry

_DESCRIPTION_BUDGET = 500  # max chars of the registry description carried into a prompt


@dataclass(frozen=True, slots=True)
class CrossfileResult:
    """The products of one cross-file resolution pass (ADR-010).

    Stability: beta
    """

    findings: list[RuleResult]  # REG010 parity findings
    floor: frozenset[tuple[str, str]]  # (resolved-file resolved-posix, function-name) → Tier 3
    context: dict[tuple[str, str], str]  # same key → semantic-prompt context note


def _uri_to_path(uri: str) -> Path | None:
    """Convert a ``file://`` URI to a local path, or None for other schemes."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path))


def _collect_entries(py_files: list[Path], config: Config) -> list[tuple[Path, ToolRegistryEntry]]:
    """Collect (file, entry) pairs that reference an imported model or handler.

    An entry qualifies if it carries an ``input_model_ref`` or a ``handler_ref``
    — the two reference kinds the cross-file pass resolves.
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
            handler_field=config.registry.handler_field,
            description_parser=parser,
        )
        for entry in entries:
            if entry.input_model_ref is not None or entry.handler_ref is not None:
                pending.append((file_path, entry))
    return pending


def resolve_crossfile(
    py_files: list[Path],
    config: Config,
    root: Path,
    severity: Severity,
) -> CrossfileResult:
    """Resolve all cross-file references in one LSP session.

    Args:
        py_files: The files in scope for this run.
        config: Resolved configuration (``registry`` field names and ``lsp``
            server/timeout drive extraction and resolution).
        root: Project root, sent as the server's workspace folder.
        severity: Resolved severity for REG010 findings.

    Returns:
        A CrossfileResult (REG010 findings, the imported-handler Tier-3 floor,
        and per-handler semantic context). Empty when no entry references an
        imported symbol.

    Raises:
        LSPError: The language server could not be started or failed during the
            run. The caller reports it as graceful degradation.

    Stability: beta
    """
    pending = _collect_entries(py_files, config)
    if not pending:
        return CrossfileResult(findings=[], floor=frozenset(), context={})

    findings: list[RuleResult] = []
    floor: set[tuple[str, str]] = set()
    context: dict[tuple[str, str], str] = {}
    field_cache: dict[tuple[str, str], frozenset[str] | None] = {}

    with LSPClient(config.lsp.server, root.resolve(), timeout=config.lsp.timeout) as client:
        for query_file in sorted({f.resolve() for f, _ in pending}):
            client.did_open(query_file)
        for file_path, entry in pending:
            # LSP needs an absolute path (as_uri() rejects relative); findings keep
            # the original file_path so their display matches the rest of the run.
            query_file = file_path.resolve()
            model_fields: frozenset[str] | None = None
            if entry.input_model_ref is not None:
                model_fields = _resolve_model_fields(
                    client, query_file, entry.input_model_ref, field_cache
                )
                if entry.description_arg_keys is not None and model_fields is not None:
                    findings.extend(parity_findings(entry, file_path, model_fields, severity))
            if entry.handler_ref is not None:
                target = _resolve_target(client, query_file, entry.handler_ref)
                if target is not None:
                    key = (target.resolve().as_posix(), entry.handler_ref.name)
                    floor.add(key)
                    context[key] = _context_note(entry, model_fields)

    findings.sort(key=lambda r: (str(r.location.file_path), r.location.line, r.location.column))
    return CrossfileResult(findings=findings, floor=frozenset(floor), context=context)


def check_input_model_parity(
    py_files: list[Path],
    config: Config,
    root: Path,
    severity: Severity,
) -> list[RuleResult]:
    """Return only the REG010 parity findings of a cross-file pass.

    A thin wrapper over ``resolve_crossfile`` for callers that want just the
    deterministic findings.

    Args:
        py_files: The files in scope.
        config: Resolved configuration.
        root: Project root (workspace folder).
        severity: Resolved severity for REG010.

    Returns:
        The REG010 findings, sorted by location.

    Raises:
        LSPError: The server could not be started or failed during the run.

    Stability: beta
    """
    return resolve_crossfile(py_files, config, root, severity).findings


def _resolve_target(client: LSPClient, query_file: Path, ref: ModelRef) -> Path | None:
    """Resolve a reference to its defining file via the server, or None."""
    # ModelRef.line is 1-based (docpact convention); LSP wants 0-based.
    locations = client.definition(query_file, ref.line - 1, ref.column)
    if not locations:
        return None
    return _uri_to_path(locations[0].uri)


def _resolve_model_fields(
    client: LSPClient,
    query_file: Path,
    ref: ModelRef,
    cache: dict[tuple[str, str], frozenset[str] | None],
) -> frozenset[str] | None:
    """Resolve an input-model reference to its field names, with caching."""
    target = _resolve_target(client, query_file, ref)
    if target is None:
        return None
    key = (target.resolve().as_posix(), ref.name)
    if key not in cache:
        cache[key] = _read_model_fields(target, ref.name)
    return cache[key]


def _read_model_fields(target: Path, class_name: str) -> frozenset[str] | None:
    """Read a resolved model's field names, or None if unreadable/not a model."""
    try:
        source = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return model_field_names(source, class_name)


def _context_note(entry: ToolRegistryEntry, model_fields: frozenset[str] | None) -> str:
    """Build a one-line cross-file context note for the semantic prompt."""
    parts = [f"Registered as tool '{entry.name}'."]
    if entry.input_model_ref is not None and model_fields is not None:
        fields = ", ".join(sorted(model_fields)) or "(none)"
        parts.append(f"Imported input model '{entry.input_model_ref.name}' fields: {fields}.")
    if entry.description_text:
        desc = " ".join(entry.description_text.split())[:_DESCRIPTION_BUDGET]
        parts.append(f"Registry description: {desc}")
    return " ".join(parts)

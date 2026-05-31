"""Resolve imported symbols via LSP for the cross-file pass (ADR-009/ADR-010).

One LSP session does all cross-file work for a run and returns a `CrossfileResult`
with three products, per ADR-010's "one resolution, two consumers":

- **findings** — REG010 (Args↔input_model parity) and REG011 (handler-signature
  parity) — the deterministic cross-file rules.
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

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse
from urllib.request import url2pathname

from docpact.lsp import LSPClient
from docpact.model.diagnostic import Severity
from docpact.parser.docstring import GoogleParser, NumpyParser
from docpact.parser.pydantic_model import model_field_names
from docpact.parser.registry import extract_tool_registry
from docpact.parser.source import extract_functions
from docpact.rules import load_builtin_rules
from docpact.rules._registry import all_rules
from docpact.rules.reg.reg010_input_model_parity import parity_findings
from docpact.rules.reg.reg011_handler_signature_parity import signature_findings

if TYPE_CHECKING:
    from docpact.config import Config
    from docpact.model.diagnostic import RuleResult
    from docpact.model.function_info import FunctionInfo
    from docpact.model.tool_registry import ModelRef, ToolRegistryEntry
    from docpact.rules._registry import RuleFn, RuleMetadata

_DESCRIPTION_BUDGET = 500  # max chars of the registry description carried into a prompt


@dataclass(frozen=True, slots=True)
class CrossfileTiming:
    """Wall-clock breakdown of one cross-file resolution pass.

    Lets `docpact bench --crossfile` show users where their cross-file time
    goes — server spawn+initialize vs. per-query resolution — so they can decide
    on their own tree whether a warm/persistent server or concurrent queries
    would help. All zero when there were no entries to resolve.

    Stability: beta
    """

    startup_seconds: float = 0.0  # spawn + initialize (carries workspace indexing)
    query_seconds: float = 0.0  # summed wall-clock across all definition() calls
    query_count: int = 0  # number of definition() calls
    max_query_seconds: float = 0.0  # slowest single query (often the first, lazy-index)


@dataclass(frozen=True, slots=True)
class CrossfileResult:
    """The products of one cross-file resolution pass (ADR-010).

    Stability: beta
    """

    findings: list[RuleResult]  # REG010 + REG011 cross-file findings
    floor: frozenset[tuple[str, str]]  # (resolved-file resolved-posix, function-name) → Tier 3
    context: dict[tuple[str, str], str]  # same key → semantic-prompt context note
    timing: CrossfileTiming = field(default_factory=CrossfileTiming)  # bench diagnostics


def _uri_to_path(uri: str) -> Path | None:
    """Convert a ``file://`` URI to a local path, or None for other schemes.

    Uses ``url2pathname`` so the Windows drive-letter form converts correctly
    (``file:///C:/x`` → ``C:\\x``), not just POSIX paths; it also handles the
    percent-decoding. On POSIX it is effectively ``unquote``.
    """
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return Path(url2pathname(parsed.path))


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
) -> CrossfileResult:
    """Resolve all cross-file references in one LSP session.

    Resolves each entry's ``input_model`` (REG010 parity) and ``handler`` (the
    Tier-3 floor, semantic context, and REG011 signature parity). Per-rule
    severities are read from config; a rule set to ``off`` contributes no
    findings but the floor and context are always computed.

    Args:
        py_files: The files in scope for this run.
        config: Resolved configuration (``registry`` field names, ``lsp``
            server/timeout, and per-rule severities).
        root: Project root, sent as the server's workspace folder.

    Returns:
        A CrossfileResult (REG010/REG011 findings, the imported-handler Tier-3
        floor, and per-handler semantic context). Empty when no entry references
        an imported symbol.

    Raises:
        LSPError: The language server could not be started or failed during the
            run. The caller reports it as graceful degradation.

    Stability: beta
    """
    pending = _collect_entries(py_files, config)
    if not pending:
        return CrossfileResult(findings=[], floor=frozenset(), context={})

    load_builtin_rules()
    rules = all_rules()
    reg010_sev = _severity(config, rules, "REG010")
    reg011_sev = _severity(config, rules, "REG011")

    findings: list[RuleResult] = []
    floor: set[tuple[str, str]] = set()
    context: dict[tuple[str, str], str] = {}
    field_cache: dict[tuple[str, str], frozenset[str] | None] = {}
    func_cache: dict[str, dict[str, FunctionInfo]] = {}

    log_file = Path(config.lsp.log) if config.lsp.log else None
    client = LSPClient(
        config.lsp.server, root.resolve(), timeout=config.lsp.timeout, log_file=log_file
    )
    with client:
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
                if (
                    reg010_sev != Severity.OFF
                    and entry.description_arg_keys is not None
                    and model_fields is not None
                ):
                    findings.extend(parity_findings(entry, file_path, model_fields, reg010_sev))
            if entry.handler_ref is not None:
                target = _resolve_target(client, query_file, entry.handler_ref)
                if target is not None:
                    key = (target.resolve().as_posix(), entry.handler_ref.name)
                    floor.add(key)
                    context[key] = _context_note(entry, model_fields)
                    if reg011_sev != Severity.OFF:
                        handler = _resolve_handler_fn(target, entry.handler_ref.name, func_cache)
                        if handler is not None:
                            findings.extend(
                                signature_findings(
                                    entry, file_path, handler, model_fields, reg011_sev
                                )
                            )

    findings.sort(key=lambda r: (str(r.location.file_path), r.location.line, r.location.column))
    timing = CrossfileTiming(
        startup_seconds=client.startup_seconds,
        query_seconds=client.query_seconds,
        query_count=client.query_count,
        max_query_seconds=client.max_query_seconds,
    )
    return CrossfileResult(
        findings=findings, floor=frozenset(floor), context=context, timing=timing
    )


def _severity(config: Config, rules: dict[str, tuple[RuleMetadata, RuleFn]], code: str) -> Severity:
    """Resolve a rule's severity from config, defaulting to its registered severity."""
    meta = rules[code][0]
    return config.rule_severities.get(code, meta.default_severity)


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


def _resolve_handler_fn(
    target: Path, name: str, cache: dict[str, dict[str, FunctionInfo]]
) -> FunctionInfo | None:
    """Return the module-level handler function in target by name, with caching."""
    key = target.resolve().as_posix()
    if key not in cache:
        cache[key] = _read_functions(target)
    return cache[key].get(name)


def _read_functions(target: Path) -> dict[str, FunctionInfo]:
    """Extract module-level functions of a file as a name→FunctionInfo map.

    Returns an empty map when the file cannot be read or parsed — the handler is
    then unresolved and REG011 is skipped (under-enforce, never guess).
    """
    try:
        functions = extract_functions(target)
    except (OSError, SyntaxError):
        return {}
    return {f.name: f for f in functions if f.containing_class is None}


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

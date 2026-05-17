# docpact

A linter, validator, and formatter for Python docstrings, designed for the audiences that consume docstrings as machine-readable contracts: MCP clients, coding agents, and CI pipelines.

## Status

**Pre-implementation.** v0.1 specification is complete. Implementation has not started.

The current artifacts in this repository are:

- [`docs/spec/docpact-spec.md`](docs/spec/docpact-spec.md) — the full specification
- [`docs/adr/`](docs/adr/) — architecture decision records documenting why specific choices were made

## What docpact does

Python functions exposed as MCP tools, FastAPI routes, or consumed by coding agents publish their contracts through docstrings. Those docstrings are now read by machines making consequential decisions: which tool to call, which arguments to pass, whether a proposed code modification is safe.

docpact validates that what the docstring says is structurally consistent with what the code does, that required information is present for the audience that will consume it, and that conflicts between sources of metadata (decorator vs. docstring, type vs. prose) are surfaced rather than silently inconsistent.

It runs in pre-commit hooks and CI, fails fast on drift, and provides safe automated fixes for the unambiguous cases.

## What docpact does NOT do

- It does not replace ruff, ty, or any type checker. It validates the docstring layer specifically.
- It does not verify behavioral correctness. It checks structural consistency. See spec §1.4.
- It does not import the code under analysis. All checks are static.
- It does not, in v0.1, perform LLM-based semantic analysis. That mode is designed in the spec but explicitly deferred. See spec §5.3 and §12.2.

## Documentation

| Document | Purpose |
|---|---|
| [Specification](docs/spec/docpact-spec.md) | Full design specification. Source of truth for what docpact is. |
| [ADR index](docs/adr/README.md) | Architecture decision records. Why each significant choice was made. |
| [ADR-001](docs/adr/ADR-001-implementation-language.md) | Implementation language decision for v0.1 (Python + griffe). |

## License

MIT (intended). LICENSE file to be added before first release.

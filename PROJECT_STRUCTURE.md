# Project structure

This document describes the layout of the docpact repository and the purpose of each directory. It is intended for contributors and for future-self orientation; users should look at the [README](README.md) and [specification](docs/spec/docpact-spec.md) instead.

## Top level

```
docpact/
├── README.md              ← user-facing project entry point
├── PROJECT_STRUCTURE.md   ← this file
├── pyproject.toml         ← package metadata, dependencies, tooling config
├── .gitignore             ← standard Python ignores
├── docs/                  ← specification and ADRs
├── src/docpact/           ← implementation
└── tests/                 ← test suite
```

The `src/`-layout (rather than placing `docpact/` at the repository root) follows modern Python packaging conventions. It prevents accidental imports from the repository root during development and makes it impossible to import the package without installing it. Recommended by the Python Packaging Authority since 2020.

## docs/

```
docs/
├── spec/
│   └── docpact-spec.md   ← the full specification
└── adr/
    ├── README.md         ← ADR index and process
    ├── template.md       ← template for new ADRs
    └── ADR-NNN-*.md      ← individual decision records
```

The specification is the source of truth for **what docpact is**. The ADRs document **why** specific implementation choices were made when the spec admits multiple valid answers.

ADRs are append-only. Accepted ADRs are not edited except for typo fixes and adding `Superseded by` links. Material changes require a new ADR that supersedes the previous.

## src/docpact/

```
src/docpact/
├── __init__.py            ← package marker, version export
├── __main__.py            ← entry point for `python -m docpact`
├── cli.py                 ← click-based CLI (check, generate, show-schema)
├── config.py              ← configuration loading (pyproject.toml / docpact.toml)
├── tiers.py               ← tier assignment per spec §10
├── testing.py             ← public testing API (see spec §14.1)
│
├── model/                 ← pure data types (no behavior)
│   ├── __init__.py
│   ├── function_info.py   ← FunctionInfo, ParameterInfo, DecoratorInfo
│   ├── parsed_docstring.py ← ParsedDocstring, Section, SectionEntry
│   └── diagnostic.py      ← RuleResult, Fix, Severity, SourceLocation
│
├── parser/                ← source and docstring parsing
│   ├── __init__.py
│   ├── source.py          ← stdlib ast → FunctionInfo
│   └── docstring.py       ← griffe → ParsedDocstring (Google style in v0.1)
│
├── rules/                 ← rule implementations
│   ├── __init__.py
│   ├── _registry.py       ← rule registration and lookup
│   ├── doc/               ← DOC namespace rules
│   │   ├── doc001_missing_docstring.py
│   │   ├── doc007_param_mismatch.py
│   │   └── ... (one file per rule)
│   ├── mcp/               ← MCP namespace rules
│   │   └── mcp001_decorator_docstring_conflict.py
│   └── (fix/, heur/, ty/, sem/ namespaces reserved)
│
└── output/                ← diagnostic formatters
    └── __init__.py        ← format_text, format_json, format_summary
                             (split into submodules when SARIF ships in v0.2)
```

### Design rules for this layout

**Pure data in `model/`.** No methods beyond dataclass essentials. No business logic. Rules transform model objects; the model objects do not act on themselves.

**Each rule is one file under `rules/<namespace>/`.** File names follow the pattern `<code_lowercase>_<descriptive_slug>.py`. The rule itself is registered via `@register(RuleMetadata(...))`. Adding a rule means creating one file and importing it from the namespace's `__init__.py`. No central catalog to keep in sync.

**`parser/` is the only place that touches AST and griffe.** Everything downstream operates on the model types. This is the abstraction line that allows future implementation changes (e.g., the parser being replaced with a Rust extension via PyO3) without rule changes.

**`testing.py` is the only stable user-facing module besides `cli.py`.** Internal types (everything under `model/`, `parser/`, `rules/`) are explicitly non-stable per spec §18.6. Plugin authors who want stability are deferred to v0.2+ (spec §7.5).

## tests/

```
tests/
├── conftest.py            ← shared fixtures
├── fixtures/              ← Python source files used as test inputs
│   └── (tier1/, tier2/, tier3/, ...)
├── test_parser/           ← tests for parser/source.py and parser/docstring.py
├── test_rules/            ← tests for each rule
│   ├── test_doc001.py
│   ├── test_doc007.py
│   └── ...
└── test_cli.py            ← end-to-end CLI tests
```

Test fixtures are real Python files. Each fixture is a minimal self-contained example demonstrating a specific case (a Tier 3 function missing Constraints, a function with mismatched Args, etc.). Fixtures are excluded from ruff and from the implementation's own dogfooded docpact checks (see `pyproject.toml` per-file-ignores).

Rule tests are organized one file per rule, mirroring the implementation layout. Each rule test verifies:
- Positive cases (rule fires when it should)
- Negative cases (rule does not fire when it should not)
- Fix behavior (safe and unsafe, if applicable)
- Suppression behavior (`# nodo: <code> -- reason` works)

## What is reserved or not yet built

The `heur/` namespace exists in the directory structure but contains no rules; its `__init__.py` documents the reservation, keeping the expansion path visible without committing implementation. (The `ty/` and `sem/` namespaces, once reserved here too, now ship rules — TY001–TY002 and SEM001–SEM002.)

The `pytest` extra (`pip install docpact[pytest]`) is declared in `pyproject.toml` but the plugin itself is not implemented yet (v0.2 target). The programmatic testing API (`docpact.testing`) covers current testing needs; the plugin will be a layer on top.

The semantic mode subsystem is present: `semantic/analyzer.py` plus the `model/module_info.py` extractor back the opt-in, advisory `docpact semantic` command (SEM001 function scan; SEM002 module scan). It is **never** part of `docpact check`, which stays deterministic and offline. See ADR-008, ADR-013, and ADR-015. Still designed-not-built within semantic mode: `--sample-rate`, an `any-llm` backend, response caching, and `context_files`.

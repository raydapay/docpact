# docpact — Specification

**Version:** 0.3.3  
**Status:** Active — v0.1 complete, v0.2 complete, v0.3 complete  
**Last revised:** 2026-05-19

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Why Comments Do Not Solve This](#2-why-comments-do-not-solve-this)
3. [Existing Tools and Their Limits](#3-existing-tools-and-their-limits)
4. [Proposal](#4-proposal)
5. [Scope: v0.1 and Beyond](#5-scope-v01-and-beyond)
6. [Consumers and Their Requirements](#6-consumers-and-their-requirements)
7. [Architecture](#7-architecture)
8. [Why Opinionated](#8-why-opinionated)
9. [Docstring Schema Specification](#9-docstring-schema-specification)
10. [Tier System](#10-tier-system)
11. [Fix Modes](#11-fix-modes)
12. [Operational Modes](#12-operational-modes)
13. [Integration with Existing Toolchain](#13-integration-with-existing-toolchain)
14. [Testing Docstring Contracts](#14-testing-docstring-contracts)
15. [Configuration](#15-configuration)
16. [Command-Line Interface](#16-command-line-interface)
17. [CI and Pre-Commit Integration](#17-ci-and-pre-commit-integration)
18. [Stability and Versioning](#18-stability-and-versioning)
19. [Agent Context Files](#19-agent-context-files)
20. [Code Examples](#20-code-examples)
21. [Open Questions](#21-open-questions)

---

## 1. Problem Statement

### 1.1 Docstrings are code

A docstring is not documentation attached to code. It is part of the code.

It is accessible at runtime via `__doc__`. It is consumed by frameworks that generate external interfaces — MCP tool schemas, OpenAPI specifications, Sphinx sites — directly from its content. It is read by automated systems making consequential decisions about when and how to call the function. It is the primary input to coding agents reasoning about whether a proposed change is safe.

A wrong docstring is a bug. Not a documentation gap, not a style violation — a bug with the same standing as a wrong type annotation or a violated invariant. The toolchain should treat it accordingly.

This is the foundational premise of `docpact`. Everything else follows from it.

### 1.2 Docstrings as contract

When a function is exposed as an MCP tool, its docstring becomes a published contract between the server and its clients. The client receives a schema derived from that docstring and makes decisions based on it. If the contract is incomplete, the client makes decisions with incomplete information. If the contract is wrong, the client makes decisions based on false information. Neither condition is detectable at runtime without the client already knowing what the function should do — which defeats the purpose of the schema.

When a function is consumed by a coding agent, its docstring is the primary signal the agent uses to determine whether a proposed modification is safe. An agent that reads "On the critical path for checkout; coordinated deploy required if signature changes" will treat the function differently from one with no such note. The docstring is not supplementary guidance — it is the machine-readable specification of the function's contract with its callers and modifiers.

This contract has two audiences that did not exist when Python docstring conventions were established: external consumers receiving generated schemas, and automated agents modifying the implementation. Both require more from docstrings than existing conventions provide.

### 1.3 The drift problem

The principal risk is drift: the docstring describes a contract that the implementation no longer honors. Drift is not a single failure mode. It has distinct forms with distinct causes and distinct consequences.

**Signature drift.** A parameter is renamed, added, or removed. The docstring is not updated. The contract now documents parameters that do not exist and omits parameters that do. This is detectable by static analysis without executing the code.

**Type drift.** A parameter's type annotation changes. The docstring still describes the old type semantics. The annotation and the prose description contradict each other. Type checkers validate the annotation; nothing validates the prose.

**Semantic drift.** The implementation changes behavior — a constraint is relaxed, a side effect is added, an error condition is removed. The docstring still describes the old behavior. This is the hardest form to detect automatically because it requires understanding both the implementation and the description.

**Schema drift.** A framework (FastMCP, FastAPI) generates an external schema from the docstring. The schema is published to clients. The implementation changes. The schema is not regenerated, or is regenerated from a docstring that has drifted. The published contract now describes a function that no longer exists.

Schema drift is the externally visible form and the form with direct user impact. The other forms accumulate until they produce schema drift or runtime failure.

`docpact` makes structural drift (signature and type) detectable and fixable in deterministic mode. It does not claim to detect all semantic drift — that is fundamentally hard. It flags likely semantic drift in semantic mode (deferred from v0.1; see section 5).

### 1.4 Honest framing

`docpact` makes docstring contracts structurally enforceable and flags likely semantic drift. It does not prove behavioral correctness. Statements like "the docstring is consistent with what the code does" should be read as "consistent with the function's signature and structure" — not as a guarantee about runtime behavior. The structural guarantees are valuable on their own; overclaiming weakens trust without adding capability.

---

## 2. Why Comments Do Not Solve This

Inline comments are the oldest form of function-level knowledge capture. They are also the most fragile.

**Comments are not structured.** There is no schema. A comment can say anything in any format. It cannot be validated against the function signature, cannot be parsed reliably, and cannot be consumed programmatically without heuristics.

**Comments do not survive refactoring.** When a function is renamed, its comments do not follow. When parameters change, no tool warns that a comment referring to the old parameter name is now stale.

**Comments are not testable.** A doctest in a docstring can be executed. A comment claiming a function returns a sorted list cannot be verified. Comments make promises the toolchain cannot hold.

**Comments are not enforced.** No CI system fails because a comment is missing or wrong. A comment expressing a critical invariant has the same weight in the pipeline as `# TODO: fix later`.

**Comments are not accessible at runtime.** `function.__doc__` returns the docstring. Comments are stripped from compiled bytecode. Frameworks that generate schemas from function metadata cannot read comments. The entire class of tooling `docpact` integrates with — FastMCP, FastAPI, mkdocstrings — operates on docstrings, not comments.

**Comments are not audience-aware.** They are written for whoever is reading the source file at that moment. They carry no signal about whether a piece of knowledge is relevant to an MCP client, a coding agent, a human reviewer, or a test harness.

Docstrings solve the runtime accessibility problem and have conventional structure and toolchain support. The remaining problem is that existing docstring conventions were designed before function interfaces became consumed by automated systems making consequential decisions about when and how to call them. `docpact` closes that gap.

---

## 3. Existing Tools and Their Limits

### Python ecosystem

**pydocstyle.** Checks PEP 257 compliance. Verifies that docstrings exist and follow surface conventions. Does not parse sections, does not validate parameter lists against signatures, has no concept of audiences or tiers.

**interrogate.** Measures docstring coverage as a percentage. Reports whether docstrings exist, not whether they are correct.

**darglint.** Validates that documented parameters and return values match the function signature. The closest existing tool. Limitations: no tier system, no stability signals, no MCP-awareness, no fix mode, limited section support beyond Args/Returns/Raises. Development activity has been low.

**griffe.** A library for extracting and parsing Python docstrings in Google, NumPy, and Sphinx styles. Powers mkdocstrings. Not a linter — it is a parsing foundation. `docpact` uses griffe as its parsing dependency.

**mypy / ty.** Type checkers. Validate type annotations but have no visibility into docstring content. `docpact` complements ty, not replaces it.

**ruff.** Lints and formats Python code. Has rules for some docstring surface properties (D-series, ported from pydocstyle). Does not parse docstring sections or validate content against signatures. Ruff is the closest architectural analog — `docpact` borrows ruff's configuration model, fix modes, and error code conventions.

### FastMCP

FastMCP extracts the free-form text above the `Args` section as the MCP tool description and maps `Args` entries to parameter descriptions in the generated JSON schema. It is the runtime consumer of docstrings for MCP-exposed functions.

FastMCP performs no validation. It accepts whatever is present and passes it through. FastMCP also supports descriptions via decorator arguments (`@mcp.tool(description="...")`). The two approaches produce identical runtime behavior but can diverge silently if both are present with different content. No existing tool detects this condition.

`docpact` is the pre-flight validator upstream of FastMCP's runtime consumption.

### Other languages

JSDoc/TSDoc, JavaDoc, and Rust doc comments introduced concepts not present in Python conventions:

- Stability signals (`@beta`, `@deprecated`, `@since`) — JavaDoc, TSDoc
- Audience separation (`@apiNote`, `@implNote`, `@implSpec`) — JavaDoc; clearest prior art for the internal/external consumer distinction
- Explicit failure contracts (`# Panics`, `# Safety`) — Rust
- Machine-parseable tags — TSDoc (designed for API Extractor)
- Runnable examples — Rust (doctests compiled and run by `cargo test`)

None of these languages have MCP tool exposure or coding agents as first-class consumers. The concepts translate; the specifics do not.

---

## 4. Proposal

`docpact` is a linter, validator, formatter, and test utility for Python docstrings, designed around three machine consumers (MCP clients, coding agents, CI pipelines) and one human consumer (the developer who configures it).

It operates in two modes:

**Structural mode** (deterministic, fast) — AST-based parsing that validates docstring presence, section completeness, parameter consistency with signatures, and schema conformance. Suitable for pre-commit hooks and CI gates.

**Semantic mode** (LLM-based, experimental) — Analysis of docstring content for quality, usefulness, and potential to mislead. Designed in this spec but **not shipped in v0.1**. See section 5 and section 12.

`docpact` follows the ruff/ty model for configuration, error codes, and fix modes.

v0.1 is implemented in Python 3.12+ with `griffe` as the docstring parsing foundation. The implementation language is not part of the user-facing contract; a future major version may rewrite all or part of the implementation in another language (Rust via PyO3 is the most likely candidate) without changing the CLI, configuration, or output formats. See [ADR-001](../adr/ADR-001-implementation-language.md) for the full rationale.

---

## 5. Scope: v0.1 and Beyond

This specification describes the complete system. Not all of it ships in v0.1. This section names what ships first and what is deferred.

### 5.1 v0.1 — initial release

- Structural mode (deterministic checks only)
- Google and NumPy docstring parsers (`format = "google"` or `"numpy"`)
- Tiers 1, 2, 3 (Tier 4 partial: explicit configuration only, no detection)
- Rule namespaces with rules: `DOC`, `MCP`, `FIX`, `TY`, `PARSE`
- Rule namespace allocated, no rules yet: `HEUR`
- Commands: `check`, `check --fix`, `check --unsafe-fixes`, `generate`, `show-schema`, `list-rules`
- Configuration via `pyproject.toml` and `docpact.toml`
- Inline suppression via `# nodo: CODE -- reason` (configurable via `suppress_comment`)
- Pre-commit integration
- Output formats: text, JSON, SARIF 2.1.0

Rationale: structural mode delivers the core differentiator (deterministic enforcement of machine-consumed contracts, MCP/decorator conflict detection, signature consistency) without depending on LLM availability, network access, or non-deterministic analysis. The MVP is useful on day one.

### 5.2 v0.2 — remaining work

- Tier 4 heuristic detection (`HEUR` namespace rules — first rules in that namespace)
- `See Also` AST symbol resolution
- Pydantic integration deepening

### 5.3 Deferred with reasoning

**DOC051 — Annotated constraint duplication** — The rule is conceptually sound (type-expressible constraints belong in `Annotated[T, ...]`, not duplicated in Constraints prose), but the numeric-substring heuristic is too coarse and produces false positives on legitimate code where the same value appears in both contexts for different reasons. The code DOC051 is reserved. See PROGRESS.md for the full rationale.

**pytest plugin** — `docpact[pytest]` extra declared; `docpact.testing` programmatic API ships in v0.1 (§14.1).

Deferred from v0.2: docpact is primarily a CI tool. In a CI-primary workflow, `docpact check src/` surfaces failures at exactly the same pipeline stage as `pytest`. The incremental value of a pytest plugin is low unless there is demand for IDE inline-diagnostics or per-function contract tests in the pytest output. The design is preserved in §14.2. Revisit if adopters request it.

### 5.4 Experimental — designed but deferred

**Semantic mode (`SEM` namespace)** is designed in this specification but deferred from v0.1 due to known operational concerns:

- **Non-determinism.** LLM outputs vary across runs and across model updates, producing flaky CI signals incompatible with merge-gate use.
- **Cost.** Per-function analysis at the scale of a real codebase has non-trivial API cost. Caching mitigates but does not eliminate it.
- **Prompt-version fragility.** Changes to the analyzer prompt invalidate prior suppressions. The original spec proposed suffixed error codes (`SEM012.v2`); a snapshot-based approach (committed `.docpact.snapshots.json` baseline files) is under consideration but unresolved.
- **Trust.** "LLM says your docstring is not useful enough" is a much harder claim to defend in code review than "docstring documents a parameter that no longer exists." Semantic mode must demonstrate value before being promoted to the default CI path.

When semantic mode does ship, it ships as opt-in, off by default, and scoped to scheduled CI runs or pre-merge gates on MCP-exposed functions — not pre-commit, not blocking gate by default. Section 12.2 describes the intended design.

### 5.5 Out of scope

- Sphinx-format parsing (deferred indefinitely; can be added if there is demand)
- A standalone `format` command separate from `check --fix` (folded into `check`)
- Third-party rule plugin API (the rule engine architecture permits it, but the API is not stabilized in v0.1; see section 7.5)
- Cross-language docstring support

### 5.6 Compatibility commitment

Every feature shipped in any version is governed by the stability commitments in section 18. Anything in v0.1 — rule codes, configuration keys, output formats — is a stable surface from v0.1 forward.

---

## 6. Consumers and Their Requirements

### 6.1 MCP Client

An MCP client receives a tool schema containing a description and parameter descriptions. It uses these to decide whether to call the tool, which arguments to provide, and how to interpret the result.

Requirements:

- **Tool description** must distinguish this tool from others in the server.
- **Parameter descriptions** must state acceptable values, constraints, and the consequence of boundary conditions. Type annotations state types; descriptions must state semantics.
- **Side effects** must be declared when present.
- **Error conditions** must be described at the semantic level, not just the exception type level.

### 6.2 Coding Agent

A coding agent modifying a codebase needs to understand not just what a function does but what it must not do, what was considered and rejected, what other parts of the codebase depend on its current behavior, and what real-world conditions affect whether modification is safe.

Requirements:

- **Implementation notes** explaining non-obvious choices.
- **Constraints** describing real-world conditions, scale, dependencies, and behavioral guarantees that affect modification decisions.
- **Cross-references** to other functions or modules that must change if this function changes.
- **Stability signals** indicating whether a function's interface is considered stable, in development, or deprecated.

When function interfaces are described by structured, validated, enforced docstrings, the codebase becomes a queryable knowledge base. A coding agent traversing it can read `See Also` to understand dependency graphs, `Constraints` to evaluate whether a proposed change is safe, and `Alternatives` to avoid re-investigating rejected approaches. The codebase is not just code to execute — it is a structured description of its own contracts, readable by any consumer that understands the schema.

### 6.3 CI Pipeline

Requirements:

- Structural validation without network access, without import-time side effects, within a time budget compatible with pre-commit hooks (< 2 seconds for typical codebases).
- Error codes suppressible selectively at file, function, or project level.
- Machine-readable output (JSON in v0.1; SARIF in v0.2) for integration with code-scanning platforms.
- Fix mode for corrections unambiguous enough to automate.

### 6.4 Human Developer

The human developer is a consumer, not the primary target. In a workflow where coding agents generate most code, the human's interaction with `docpact` is primarily through CI feedback and the configuration that defines the schema. The developer's role is to define contract requirements and to resolve conflicts that automated fixes cannot handle unambiguously.

---

## 7. Architecture

### 7.1 Layers

```
┌─────────────────────────────────────────────────────────┐
│                      CLI / API                          │
│          docpact check / generate / show-schema         │
├─────────────────────────────────────────────────────────┤
│                    Rule Engine                          │
│   Tier assignment → Rule selection → Diagnostic emit    │
├──────────────────────────┬──────────────────────────────┤
│    Structural Analyzer   │  Semantic Analyzer (v0.2+)  │
│    (AST + parsed doc)    │  (experimental, off by      │
│                          │   default; see section 12)  │
├──────────────────────────┴──────────────────────────────┤
│                   DocstringParser                       │
│         (abstract interface, format-specific impls)     │
│                                                         │
│   GoogleParser    NumPyParser    SphinxParser*            │
│   (v0.1)          (v0.1)        (* deferred)             │
├─────────────────────────────────────────────────────────┤
│              Python AST + griffe                        │
│      Source parsing, signature extraction,              │
│      decorator detection, symbol resolution             │
└─────────────────────────────────────────────────────────┘
```

### 7.2 DocstringParser interface

The `DocstringParser` interface is the boundary between format-specific parsing and the rule engine. The rule engine operates exclusively on `ParsedDocstring` objects.

```python
# Conceptual interface — not an implementation prescription

class ParsedDocstring:
    summary: str
    description: str | None
    sections: dict[str, Section]
    raw: str

class Section:
    name: str
    entries: list[Entry]           # for Args, Raises, See Also (key: value)
    body: str | None               # for Notes, MCP, Alternatives (freeform)

class DocstringParser(Protocol):
    def parse(self, raw: str) -> ParsedDocstring: ...
    def format_name(self) -> str: ...  # "google" | "numpy" | "sphinx"
```

This abstraction means additional parser implementations can be added without modifying any rule. v0.1 ships Google and NumPy parsers. The config key `format = "google"` or `"numpy"` selects the parser; `"sphinx"` is deferred indefinitely.

### 7.3 Rule engine

Rules are pure functions. They receive function metadata and a parsed docstring and return diagnostics. They do not modify files. The fix engine applies `Fix` objects separately.

```python
class RuleResult:
    code: str
    message: str
    location: SourceLocation
    fix: Fix | None
    unsafe_fix: Fix | None

def rule_DOC007(
    func: FunctionInfo,
    doc: ParsedDocstring,
    config: RuleConfig,
) -> list[RuleResult]: ...
```

### 7.4 Tier assignment

Tier assignment is a pure function of `FunctionInfo`. It inspects decorator names, function name prefix, class membership, and module-level context. It is the first operation the rule engine performs before selecting which rules apply.

Tier assignment results can be overridden per-file in configuration. The assigned tier is always visible in JSON output to aid debugging.

### 7.5 Rule registration and extensibility

Built-in rules ship as part of the docpact binary. They are registered via a static catalog at build time. The catalog is the source of truth for rule codes, defaults, fix availability, and documentation links.

**Third-party rules are not supported in v0.1.** The rule engine architecture (pure functions over `ParsedDocstring`) does not preclude them, but the API surface is not stabilized. Teams needing project-specific rules in v0.1 should write them as separate tools consuming the same parsed-docstring representation.

A stable plugin API is a v0.2+ candidate, gated on whether it can be defined without exposing internal data structures that the implementation needs to refactor freely.

### 7.6 Semantic analyzer

When implemented (post-v0.1), the semantic analyzer is architecturally isolated from the structural analyzer. It emits `list[RuleResult]` with codes in the `SEM` namespace; the rule engine treats these identically to structural results (suppression, severity, and output routing all apply). It is never invoked by `docpact check` — only by `docpact semantic`.

Two scan modes, each with its own input contract:

- **Function-level:** receives `(FunctionInfo, ParsedDocstring, SemanticConfig)`. Context is self-contained — the function body and its docstring are sufficient.
- **Module-level:** receives `(ModuleInfo, SemanticConfig, ProjectContext)`. Requires project-level context to judge whether a module docstring correctly situates the module in the architecture. `ProjectContext` is assembled once per run from the files listed in `[tool.docpact.semantic] context_files`.

LLM I/O is abstracted behind an internal `SemanticBackend` protocol:

```python
class SemanticBackend(Protocol):
    def complete(self, messages: list[dict[str, str]], model: str) -> str: ...
```

Concrete adapters ship with the `docpact[semantic]` extra:

- `OpenAICompatBackend` — targets any OpenAI-compatible HTTP endpoint (OpenRouter, Cloudflare AI Gateway, Bifrost, Ollama, vLLM, private deployments). Requires only the `openai` SDK.
- `AnyLLMBackend` — in-process routing via `any-llm-sdk`, which wraps official provider SDKs. Install provider extras explicitly: `docpact[semantic,anthropic]`, `docpact[semantic,openai]`, etc.

The protocol seam means either adapter can be replaced without changing any calling code.

---

## 8. Why Opinionated

Configuration-heavy tools shift decision-making to the user. When every rule is optional and every format is supported equally, the tool provides mechanism without guidance. Each project invents its own conventions, defeating the purpose of a shared tool.

`docpact` is opinionated:

**One baseline format.** Google-style docstrings are the default. NumPy is also supported via `format = "numpy"`. Sphinx is not on the roadmap.

**Decorator and docstring are mutually exclusive for MCP metadata.** A function may declare its MCP description via `@mcp.tool(description="...")` or via a docstring `MCP:` section, not both. If both are present, `docpact` reports `MCP001`. The resolution (decorator wins) is available as an unsafe fix.

**Tiers are determined by context, not configuration.** The tier of a function is determined by its decorator, name, or containing class — not a per-function configuration comment. This makes tier assignment consistent and auditable. Per-file overrides exist but are visible in config.

**Safe fixes are conservative.** A safe fix never changes semantic content.

These choices can be overridden in `[tool.docpact]` configuration. The defaults are designed to be correct without configuration.

---

## 9. Docstring Schema Specification

### 9.1 Section inventory

Sections are identified by their header line followed by a colon, consistent with Google style. All sections are optional unless tier rules (section 10) require them.

#### Universal sections (all tiers)

**Summary** *(implicit — first line)*
Single sentence. Imperative mood. Must not begin with "This function", "This method", "Returns a". Period required for one-liners; omitted when a body follows.

**Args**
One entry per parameter. Format: `param_name: description`. Type information omitted (present in annotations). `*args` and `**kwargs` documented when their contents are meaningful. Each entry must correspond to an actual parameter. Parameters in the signature but absent from `Args` are an error at Tier 2 and above.

**Returns**
Description of the return value semantics. Omitted for `None` return type. Must not simply restate the type annotation.

**Raises**
One entry per exception type the function may raise under documented conditions. Format: `ExceptionType: condition`. Documents caller-observable exceptions, not internal exceptions always caught. Functions that do not raise may explicitly state so (see section 9.3).

**Examples**
One or more usage examples. Valid Python expressions are run as doctests when `--doctest` is specified.

#### Extended sections (Tier 2 and above)

**Constraints**

Real-world conditions outside the type system — operational context, scale, resource expectations, dependencies, risk factors, and behavioral guarantees — that affect when, whether, or how this function can be safely called or modified.

This section is for considerations a coding agent or human reviewer must weigh when deciding to call, refactor, or replace the function. **It is not for preconditions expressible as type constraints.** If a constraint can be encoded as `Annotated[T, ...]`, a Pydantic `Field` validator, or `Literal[...]`, it belongs in the type, not here. Duplication will be reported as `DOC051` (deferred — see §5.3).

Examples of what belongs in Constraints:

- **Scale:** `Tested at up to 10K records. Performance at 1M+ records not validated.`
- **Dependencies:** `Requires Redis connection. Falls back to in-memory cache with degraded consistency.`
- **Deployment risk:** `On the critical path for checkout. Coordinated deploy required if signature changes.`
- **Transactional behavior:** `Idempotent within a transaction; unsafe to retry across transactions.`
- **Resource cost:** `Loads ~500MB for typical inputs. Not suitable for memory-constrained environments.`
- **External system:** `Network call to third-party API. Subject to rate limits (1000/hr).`
- **Behavioral guarantee:** `Preserves insertion order. Callers may rely on this.`
- **Operational precondition:** `Caller must hold a valid session lock acquired via session.acquire().`

Examples of what does **not** belong in Constraints:

- Max length, regex pattern, value range → use `Annotated[str, MaxLen(N)]`, `Annotated[str, Pattern(r"...")]`, `Annotated[int, Ge(0), Le(100)]`
- Nullability → use `T | None`
- Enumeration of allowed values → use `Literal["a", "b", "c"]`
- "Must be a UTF-8 string" → this is the `str` type itself
- "Must be a positive integer" → use `Annotated[int, Gt(0)]`

The distinction is: types describe values; Constraints describes the world the function operates in. If a coding agent could verify the condition by reading only the annotation, it belongs in the type. If verifying the condition requires knowledge the type system does not carry — runtime state, system context, operational history, deployment topology — it belongs in Constraints.

**Mutates**
Explicit enumeration of state the function modifies outside its return value. Omitted when the function has no side effects. Example: `Modifies the session cache. Appends to the audit log.`

**Stability**
One of: `stable`, `beta`, `internal`, `deprecated`. Default when absent: `stable` for public functions, `internal` for `_`-prefixed functions. `deprecated` requires a `See Also` entry pointing to the replacement.

**See Also**
Cross-references to related functions, classes, or modules. Format: `module.function — reason for reference`. Used by agents to identify parts of the codebase affected by a change.

#### Tier 3 sections (MCP-exposed functions)

**MCP**
Mutually exclusive with `description=` in the `@mcp.tool()` decorator. Contains the natural-language description of the tool as it will appear to MCP clients. May differ from the Summary — the summary is for code readers, the MCP section is for tool-calling agents.

#### Optional sections (any tier)

**Notes**
Freeform implementation notes. The appropriate place for "why this implementation and not another."

**Alternatives**
Approaches considered and rejected, with reasons.

**References**
External sources (papers, standards, issue tracker links) relevant to the implementation.

### 9.2 Section ordering

Canonical order (enforced by `--fix`):

```
Summary

[Extended description paragraphs]

Args:
Returns:
Raises:
Constraints:
Mutates:
Stability:
MCP:
Notes:
Alternatives:
References:
See Also:
Examples:
```

### 9.3 Empty section canonical form

A required section that legitimately has no content uses an explicit empty form rather than being omitted. This satisfies the section-present rule and signals deliberate absence rather than oversight.

```
Raises:
    None.

Constraints:
    None beyond type annotations.

Mutates:
    None.
```

Sections marked with `None.` or an equivalent explicit statement pass structural checks. Sections that are simply absent fail with the corresponding `DOC012` (missing required section).

Rule `DOC013` (warning) fires when an empty section uses a non-canonical form (e.g., `Raises:` with a blank body, or `Raises: N/A`). The safe fix replaces the body with `None.`.

---

## 10. Tier System

The tier of a function determines which sections are required, which are recommended (warnings), and which are ignored.

### 10.1 Tier assignment rules

Tier assignment is deterministic. Rules are evaluated in order; the first match wins.

1. **Decorated with `@mcp.tool`, `@mcp.resource`, or `@mcp.prompt`** → Tier 3. Applies regardless of containing class or naming.
2. **In a file explicitly configured for Tier 4** (`[tool.docpact.tiers]`) → Tier 4. See section 10.5.
3. **Method on a class whose name begins with `_`** → Tier 1. The class itself is internal; its methods inherit that audience.
4. **Function or method whose name begins with `_`** (other than dunder methods) → Tier 1.
5. **Dunder methods** (`__init__`, `__repr__`, `__eq__`, etc.) → inherit the tier of the containing class. `__init__` on a Tier 2 class is Tier 2. `__init__` on a `_`-prefixed class is Tier 1.
6. **`@property`, `@cached_property`, `@staticmethod`, `@classmethod` decorators** → inherit the tier of the containing class. The property/method-class decorator does not change tier.
7. **All other public functions and methods** → Tier 2.

### 10.2 Tier 1 — Internal functions

**Required:** Summary only.
**Recommended:** Args, Returns when non-trivial.

### 10.3 Tier 2 — Package-public functions and methods

**Required:** Summary, Args (all parameters), Returns (if non-None).
**Recommended:** Raises, Constraints, Stability.

### 10.4 Tier 3 — MCP-exposed functions

**Required:** Summary, Args (all parameters), Returns, Raises, Constraints, Stability, and either `MCP:` section or `description=` in decorator (not both).
**Recommended:** Mutates, See Also.

### 10.5 Tier 4 — FastAPI routes exposed via `FastMCP.from_fastapi()`

**Trigger (v0.1):** Explicit declaration in configuration:

```toml
[tool.docpact.tiers]
"src/routes.py" = 4
```

**Trigger (v0.2+):** Heuristic detection. See section 12.3.

**Required:** Same as Tier 3. `MCP001` fires if both a docstring `MCP:` section and a FastAPI route `summary=`/`description=` are present with different content.

---

## 11. Fix Modes

Consistent with ruff conventions.

### No flag — report only

Reports all errors and warnings. Exits non-zero if any errors are present. Does not modify files.

### `--fix` — safe fixes

Applies fixes that are unambiguous and do not alter semantic content:

| Condition | Fix |
|---|---|
| Parameter in signature missing from Args | Add stub: `param_name: [FILL]` |
| Parameter in Args not present in signature | Remove the stale entry |
| Sections out of canonical order | Reorder to canonical order |
| Both decorator and docstring MCP section, identical content | Remove docstring MCP section |
| Summary begins with "This function" / "This method" | Remove the prefix, capitalize next word |
| Trailing whitespace in docstring lines | Remove |
| Empty section with non-canonical form (`DOC013`) | Replace with `None.` |
| Constraint duplicates `Annotated` metadata (`DOC051`, deferred) | Remove the duplicating prose entry |

Conditions where `--fix` reports an error and does not apply a fix:

| Condition | Error | Reason |
|---|---|---|
| Both decorator and docstring MCP section, different content | `MCP001` | Semantic conflict |
| Parameter documented with wrong name (typo suspected) | `DOC014` | Cannot determine intent |

### `--unsafe-fixes` — opinionated resolutions

Requires `--fix`. Applies fixes that involve a documented choice:

| Condition | Fix | Posture |
|---|---|---|
| `MCP001`: both present with different content | Decorator wins, docstring section removed | Decorator is closer to runtime behavior |
| Missing Stability on Tier 3 function | Insert `Stability: stable` | Conservative default |

Each unsafe fix is individually suppressible via `# noqa: CODE`.

---

## 12. Operational Modes

### 12.1 Structural mode (v0.1, default)

Operates on source files via AST and docstring parsing. No imports, no network access, no LLM calls.

**Checks:**
- Section presence and ordering
- Parameter list consistency with function signatures
- Type annotation contradictions: `-> None` with substantive Returns prose (`TY001`); non-None annotation with canonical-empty Returns (`TY002`)
- Decorator / docstring MCP metadata conflicts
- Stability field validity
- Summary line heuristics (length, prohibited prefixes, imperative mood detection)
- Constraint section presence on Tier 3 functions
- `Annotated` constraint duplication in Constraints prose (`DOC051`, deferred — see §5.3)
- Pydantic model fields missing `Field(description=...)` (`DOC050`)

**Performance target:** < 2 seconds on a 50,000-line codebase.

**Dependencies:** Python AST, griffe.

### 12.2 Semantic mode (designed; not in v0.1)

Invoked via `docpact semantic`. Never runs as part of `docpact check`. Requires explicit invocation and configured LLM credentials. Designed for scheduled CI runs (weekly, nightly) — not pre-commit, not a blocking merge gate by default.

Emits `SEM`-namespaced `RuleResult` objects through the standard rule pipeline. Suppression (`# nodo: SEM001 -- reason`), severity configuration, `--changed-only`, and `--sample-rate` all work identically to structural mode.

#### Two scan modes

**Function-level** evaluates docstring content against the function body. Context is self-contained — no project-level files needed. Rubric dimensions (categorical verdicts: `good` / `weak` / `missing`):

| Dimension | Question |
|---|---|
| Summary accuracy | Does it describe what the function *does*, not restate the name? |
| Args signal | Do descriptions add information beyond what the type annotation already states? |
| Returns meaning | Does it explain what the value *means*, not just its type? |
| Contracts | Are non-obvious preconditions, side effects, and error conditions documented? |

Cache key: `(function_content_hash, prompt_version, model_id)`.

**Module-level** evaluates whether a module docstring correctly situates the module in the project. Requires project-level context. Rubric dimensions:

| Dimension | Question |
|---|---|
| Scope accuracy | Does the description match what the module actually contains — neither too narrow nor too broad? |
| Orientation | Does it help a reader decide when and why to use this module vs. sibling modules? |

Cache key: `(file_content_hash, project_context_hash, prompt_version, model_id)`. The `project_context_hash` covers all files in `context_files` — a change to any of them invalidates module-level cache entries even if the module itself did not change. Module-level scan should therefore run less frequently than function-level (or be triggered by changes to `context_files`).

A finding is emitted when any rubric dimension scores `missing`. `weak` is reported as a warning by default. Both thresholds are configurable (see §15.1).

#### Backend architecture

LLM I/O is abstracted behind an internal `SemanticBackend` protocol (see §7.6). Two adapters ship with `docpact[semantic]`:

- **`openai-compat`** — targets any OpenAI-compatible HTTP endpoint. Covers OpenRouter, Cloudflare AI Gateway, Bifrost, Ollama, vLLM, and any private deployment. Requires only the `openai` SDK.
- **`any-llm`** — in-process routing via `any-llm-sdk`, which wraps official provider SDKs. No proxy infrastructure required. Provider extras installed explicitly: `docpact[semantic,anthropic]`, `docpact[semantic,openai]`, etc.

#### Known risks and mitigations

| Risk | Mitigation |
|---|---|
| Non-determinism across runs | Categorical verdicts (`good`/`weak`/`missing`), not floats; `temperature=0` |
| Prompt-version fragility | Cache key includes `prompt_version`; changing the prompt invalidates prior entries |
| Cost at scale | Content-hash caching; `--changed-only`; `--sample-rate` |
| Reduced trust in LLM-as-judge | Warning severity by default; findings are advisory until opted into error |

**Unresolved:** suppression of SEM findings across prompt-version changes (snapshot-baseline approach is a candidate but not finalised). Prompt versioning scheme TBD.

When semantic mode ships, it ships off by default. `docpact check` is never affected. The rule engine architecture, namespace allocation, and severity model already account for `SEM` rules.

### 12.3 Heuristic rules (`HEUR` namespace)

Some valuable checks cannot be made fully deterministic without false positives. Detecting whether a module is passed to `FastMCP.from_fastapi()`, whether a function is a FastAPI route based on decorator patterns, whether a class is conceptually private despite a public name — these are inference problems where confident wrong answers are worse than no answer.

`docpact` separates these into the `HEUR` rule namespace.

**Properties of `HEUR` rules:**

- Default severity: **warning** (not error). A heuristic finding never blocks CI by default.
- Configurable severity per rule and globally.
- Documented in the rule catalog as heuristic, with the heuristic logic stated explicitly.
- Suppressible via `# noqa: HEUR_NNN` like any other rule.

**Configuration:**

```toml
# Per-rule severity
[tool.docpact.rules]
HEUR001 = "warning"  # default
# HEUR001 = "off"    # disable detection entirely
# HEUR001 = "error"  # treat heuristic as authoritative

# Or global default for all HEUR rules
[tool.docpact]
heuristics = "warning"
```

**v0.1 ships no `HEUR` rules.** The namespace is allocated and the configuration semantics are defined so that v0.2 additions (Tier 4 FastAPI detection, implicit `Mutates` inference) can ship without configuration-shape changes.

---

## 13. Integration with Existing Toolchain

### 13.1 ty (type checker)

`docpact` complements ty, not replaces it. The `TY` rule namespace catches contradictions between type annotations and docstring prose that neither tool detects alone.

**Shipped in v0.1 (annotation-based):**

- **TY001** (ERROR): function annotated `-> None` but `Returns:` section has substantive content. The annotation promises no return value; the prose contradicts it. Skips canonical-empty bodies (`None.`, `N/A`).
- **TY002** (WARNING): non-`None` return annotation but `Returns:` body is exactly `None.` (canonical empty). `DOC012` is satisfied by presence; TY002 catches the coherence failure DOC012 misses.

Both rules operate entirely on AST annotations and parsed docstring content. No external ty output is consumed; no CLI flag required.

**Deeper ty integration (deferred):**

Consuming ty's type-graph output (e.g., `--ty-output path/to/ty.json`) to cross-validate constraint narrowing — detecting when a docstring `Constraints` entry expresses something the annotation already encodes — is not yet implemented. If demand emerges, this is the natural next step in the TY namespace.

### 13.2 Pydantic and `Annotated`

`Annotated[T, ...]` and Pydantic `Field(description=..., ...)` are structured, machine-readable specifications at the type level. They are the canonical home for any constraint that can be expressed as a property of a value.

The rule is one-way: any constraint expressible in `Annotated` or `Field` belongs there, not in the docstring `Constraints` section. `DOC051` is designed to enforce this — deferred until a detector more precise than numeric-value heuristics is available (see §5.3).

For Pydantic model parameters specifically:

- The `Args` entry documents the parameter at the semantic level (what it represents, behavioral context).
- Field-level documentation lives in `Field(description=...)` on the model.
- `DOC050` warns when a model field lacks `Field(description=...)`. Severity configurable.

This makes `docpact`, `Annotated`, and Pydantic a unified contract layer: values and their syntactic constraints in the types; real-world and behavioral constraints in `Constraints`; both validated together.

### 13.3 FastMCP

`docpact` runs upstream of FastMCP's runtime schema generation:

- `docpact` ensures the docstring is structurally correct and consistent with the function signature.
- FastMCP consumes the docstring and generates the MCP schema.
- If `docpact` passes, the input to FastMCP is valid.

`docpact` validates the `MCP001` condition that FastMCP silently ignores. It does not validate the generated MCP JSON schema directly — that is a FastMCP responsibility.

### 13.4 ruff

`docpact` and ruff are complementary. ruff's D-series rules cover surface docstring properties. Projects using `docpact` should disable D-series rules to avoid redundant checks:

```toml
[tool.ruff.lint]
ignore = ["D"]
```

`docpact` does not format general Python code. ruff handles that.

---

## 14. Testing Docstring Contracts

Because docstrings are part of the code and define contracts that other systems depend on, they should be testable with the same tooling used to test the rest of the code. `docpact` provides three levels of test integration. **Programmatic assertions ship in v0.1. The pytest plugin is deferred — see §5.3.**

### 14.1 Programmatic assertions (v0.1)

`docpact` exposes a `testing` module for use in hand-written test files:

```python
from docpact.testing import (
    assert_tier,
    assert_section_present,
    assert_params_match_signature,
    assert_mcp_schema_from_docstring,
    get_parsed_docstring,
)
from myapp.tools.search import search_documents


def test_search_documents_is_tier3():
    assert_tier(search_documents, 3)


def test_search_documents_required_sections():
    assert_section_present(search_documents, "Constraints")
    assert_section_present(search_documents, "Stability")


def test_search_documents_params_match_signature():
    assert_params_match_signature(search_documents)


def test_search_documents_mcp_description():
    # assert_mcp_schema_from_docstring parses the docstring using docpact's
    # internal parser and returns the schema FastMCP *would* generate. It
    # does not import FastMCP. It does not generate or compare against a
    # running schema. It validates that the docstring contains the
    # information FastMCP needs.
    schema = assert_mcp_schema_from_docstring(search_documents)
    assert len(schema["description"]) >= 50
    assert set(schema["parameters"]) == {"query", "collection", "max_results", "include_metadata"}
```

`assert_mcp_schema_from_docstring` is named precisely: it returns what the docstring implies about the schema, not what FastMCP would actually emit. The two should match, but the test surface stays within `docpact` so it has no FastMCP version dependency.

### 14.2 pytest plugin (deferred — see §5.3)

Installing `docpact[pytest]` activates a pytest plugin that turns every function with a docstring into a collected test item:

```
PASSED  src/tools/search.py::search_documents [docpact:structural]
FAILED  src/tools/legacy.py::old_function [docpact:DOC007]
  Parameters in docstring absent from signature: ['user', 'token']
```

```toml
[tool.pytest.ini_options]
addopts = "--docpact"

[tool.docpact.pytest]
include = ["DOC", "MCP"]
run_doctests = true
```

### 14.3 Doctest execution (v0.1)

Examples sections containing valid Python expressions are runnable as doctests via:

```
docpact check --doctest src/
```

Failed doctests are reported as `DOC098` (raised an exception) or `DOC099` (output mismatch). The `[FILL]` stub marker causes `DOC099`. Generated stubs cannot pass the pipeline unmodified.

---

## 15. Configuration

Configuration follows the ruff/ty model: `pyproject.toml` is primary, with optional standalone `docpact.toml`. When both are present, `docpact.toml` wins with a warning.

### 15.1 `pyproject.toml`

```toml
[tool.docpact]
# Schema version this project targets.
schema = "1"

# Rules to enable. Prefix with ! to disable.
select = ["DOC", "MCP"]
ignore = ["DOC013"]

# Files and directories to exclude.
exclude = ["tests/", "migrations/", "**/_generated.py"]

# Docstring format: "google" (default) or "numpy".
format = "google"

# Inline suppression marker(s). Default: ["nodo"].
# Add "noqa" during migration from # noqa: syntax.
suppress_comment = ["nodo"]

# Default severity for all HEUR rules.
heuristics = "warning"

# Per-rule severity overrides.
[tool.docpact.rules]
DOC050 = "warning"
HEUR001 = "off"

# Per-file rule overrides.
[tool.docpact.per-file-ignores]
"src/legacy/**" = ["DOC", "MCP"]
"tests/**" = ["MCP001"]

# Tier assignment overrides.
[tool.docpact.tiers]
"src/public_api.py" = 2
"src/routes.py" = 4

# Pydantic field documentation severity.
[tool.docpact.pydantic]
undescribed_fields = "warning"  # error | warning | off

# Semantic scan configuration (docpact[semantic] required).
[tool.docpact.semantic]
# Backend adapter: "openai-compat" | "any-llm"
backend = "openai-compat"

# Model string — interpreted by the backend.
# openai-compat: passed as-is to the HTTP endpoint.
# any-llm: "provider/model" format, e.g. "anthropic/claude-sonnet-4-6".
model = "anthropic/claude-sonnet-4-6"

# Name of the environment variable holding the API key. Never the key itself.
api_key_env = "ANTHROPIC_API_KEY"

# Base URL for openai-compat backends. Required when backend = "openai-compat".
# api_base = "https://openrouter.ai/api/v1"
# api_base = "http://localhost:8080"   # Bifrost or other local gateway
# api_base = "http://localhost:11434/v1"  # Ollama

# Project-level context files for module-level scan.
# Relative to the project root. Directories pull in *.md files recursively.
context_files = ["README.md", "CLAUDE.md", "docs/"]

# Scan modes to run: "function" | "module" | both.
scan_modes = ["function"]

# Verdict threshold that triggers a finding.
# "missing": error only when a dimension verdict is "missing".
# "weak":    warning on "weak", error on "missing".
finding_threshold = "missing"
```

### 15.2 Inline suppression

```python
def legacy_function(x, y):  # nodo: DOC001 -- pre-docpact legacy, tracked in #412
    """Does something."""
    ...
```

The suppression marker is `nodo` by default, configurable via `suppress_comment = [...]` in `[tool.docpact]`. Using `["nodo", "noqa"]` accepts both during a migration period. The `# noqa` form was the original choice but was changed (ADR-004) because ruff's RUF100 silently strips unknown `# noqa` codes.

**Placement:** the suppression comment must be on the `def` keyword line. Placing it on the closing `) -> Type:` line silently fails — `func.line` is the `def` line.

Bare suppression without codes emits `FIX001`. Suppression with codes but without `-- reason` emits `FIX002`. Both are themselves defects.

### 15.3 Error code structure

| Prefix | Domain | Ships in |
|---|---|---|
| `DOC` | Structural docstring rules | v0.1 |
| `MCP` | MCP-specific rules (decorator conflicts, schema metadata) | v0.1 |
| `FIX` | Fix-mode diagnostics | v0.1 |
| `TY` | Annotation/docstring contradiction rules | v0.1 |
| `PARSE` | Parse-time error rules (file cannot be parsed at all) | post-v0.3 |
| `HEUR` | Heuristic rules | v0.2 (namespace allocated v0.1; no rules yet) |
| `SEM` | Semantic mode findings | Deferred (experimental) |

`PARSE` rules fire before any structural or function-level checks. If a `PARSE` rule fires for a file, all other checks for that file are skipped — structural analysis requires a valid AST. By default the `PARSE` namespace is selected (same as `DOC`, `MCP`); add `PARSE001` to `[tool.docpact.per-file-ignores]` to silence it for generated or vendored files.

Error codes with `[*]` suffix indicate a fix is available.

---

## 16. Command-Line Interface

```
docpact check    [OPTIONS] [FILES_OR_DIRS]...
docpact semantic [OPTIONS] [FILES_OR_DIRS]...
docpact generate [OPTIONS] [FILES_OR_DIRS]...
docpact show-schema [--tier {1,2,3,4}]
docpact list-rules  [--format {text,json}]
```

### `check` (v0.1)

```
  --fix                       Apply safe fixes in-place.
  --unsafe-fixes              Apply unsafe fixes. Requires --fix.
  --select CODES              Rule codes or prefixes to enable.
  --ignore CODES              Rule codes or prefixes to disable.
  --format {text,json,sarif}  Output format. Default: text.
  --exit-zero                 Always exit 0.
  --diff                      Show diff of --fix output without applying.
```

### `check` additions (future)

```
  --watch                     Re-run on file changes.
```

### `semantic` (post-v0.1)

Runs LLM-based semantic analysis. Requires `docpact[semantic]` and configured credentials. See §12.2 for full design. Never shares a code path with `check`.

```
  --scan-modes {function,module}  Scan modes to run. Overrides config. Default: ["function"].
  --changed-only REF              Restrict to .py files changed relative to REF.
  --sample-rate FLOAT             Fraction of eligible units to analyse (0.0–1.0). For cost control.
  --format {text,json}            Output format. Default: text.
  --dry-run                       Show what would be analysed without calling the LLM backend.
  --select CODES                  SEM rule codes or prefixes to enable.
  --ignore CODES                  SEM rule codes or prefixes to disable.
```

### `generate`

Generates stub docstrings for undocumented functions using signature and decorator context to determine tier and required sections. Stubs contain `[FILL]` markers.

### `show-schema`

```
docpact show-schema --tier 3

Tier 3 — MCP-exposed functions
Required:    Summary, Args, Returns, Raises, Constraints, Stability,
             MCP (or decorator)
Recommended: Mutates, See Also
Optional:    Notes, Alternatives, References, Examples
```

---

## 17. CI and Pre-Commit Integration

### 17.1 Pre-commit hook

```yaml
repos:
  - repo: https://github.com/raydapay/docpact
    rev: v0.1.0a1
    hooks:
      - id: docpact
        args: [--fix]
```

### 17.2 GitHub Actions — text/JSON gate

```yaml
name: docpact

on: [push, pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv tool run docpact check src/
```

### 17.3 GitHub Actions — SARIF gate (Code Scanning)

```yaml
- run: uv tool run docpact check src/ --format sarif --exit-zero > docpact.sarif
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: docpact.sarif
```

### 17.4 pytest in CI (deferred — see §5.3)

```yaml
- run: uv run pytest src/ --docpact --tb=short
```

### 17.5 GitHub Actions — scheduled semantic scan

Wire `docpact semantic` to a schedule trigger, not `push` or `pull_request`. It is not a merge gate by default.

```yaml
name: docpact-semantic

on:
  schedule:
    - cron: "0 3 * * 1"  # weekly, Monday 03:00 UTC
  workflow_dispatch:       # allow manual trigger

jobs:
  semantic:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # needed for --changed-only
      - uses: astral-sh/setup-uv@v3
      - run: uv tool run docpact semantic src/ --changed-only origin/main
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

Module-level scan should run at a lower frequency (monthly or on changes to `context_files`) due to higher caching cost (see §12.2). Add `--scan-modes module` in a separate job or a separate workflow.

---

## 18. Stability and Versioning

`docpact` makes the following stability commitments to its users. Teams adopting `docpact` in CI depend on these guarantees; they are not subject to change without a major version bump.

### 18.1 Error code stability

Error codes are a stable API.

- A code, once shipped, never changes its meaning.
- A code is never reused for a different rule.
- When a rule is deprecated and eventually removed, its code becomes a permanently retired identifier — never reissued for any other rule.
- New codes are appended; existing codes are not renumbered.

This matches ruff's policy. It exists because teams write `# noqa: DOC007` suppressions, CI rules, and grep patterns against these codes. A tool that renumbers codes between releases cannot be used in serious pipelines.

### 18.2 Schema versioning

The docstring schema (section inventory, tier requirements, required sections per tier) follows semantic versioning:

- **Patch:** Rule logic improvements. No schema change. No required section added or removed.
- **Minor:** New optional or recommended sections added. New tiers added. New rules shipped with default severity off, or default warning. Existing required-section sets are not changed.
- **Major:** A previously optional section becomes required. A tier's required-section set is expanded. A default severity is changed from warning to error in a way that would break existing passing codebases.

The schema major version is declared in configuration:

```toml
[tool.docpact]
schema = "1"
```

Without an explicit `schema` setting, `docpact` defaults to the schema major version current at the binary's release. CI failures at major version transitions surface at the configuration layer, not in source files. Teams pin `schema = "1"` when they want stability across `docpact` upgrades, and bump to `schema = "2"` deliberately when they are ready.

### 18.3 Migration support

When a schema major version is released, `docpact` provides:

```
docpact migrate --from 1 --to 2 src/
```

The migrate command applies mechanically-safe transformations to bring the codebase to the new schema. Cases requiring human review are reported, not silently changed. The migrate command is itself versioned and stable; running an old migrate against a newer schema is an error, not a silent no-op.

### 18.4 Configuration stability

Configuration keys in `[tool.docpact]` are stable API at the same level as error codes. New keys are added; existing keys are not renamed or repurposed within a major version. Removed keys leave a deprecation period of at least one minor version with a clear warning before they stop being recognized.

### 18.5 Output format stability

The JSON output schema is versioned. Consumers (CI scripts, dashboards) can rely on its structure within a major version. SARIF output, when introduced in v0.2, follows the SARIF spec version explicitly named in its output.

### 18.6 What is not promised

The internal data structures (`ParsedDocstring`, `RuleResult`, `FunctionInfo`) are not stable API in v0.1. They may change in any release. This is what blocks the third-party rule plugin API (section 7.5): a stable plugin API requires stabilizing these structures, and stabilizing them prematurely would constrain the implementation.

The wire protocol of any future client/server mode is not promised in v0.1.

---

## 19. Agent Context Files

`docpact` is declared in agent context files alongside `ruff` and `ty`. The following template is the recommended baseline. The same content is appropriate for `CLAUDE.md`, `AGENTS.md`, and `GEMINI.md`.

```markdown
## Code quality pipeline

All checks must pass before code is considered complete.

- **ruff** — linting and formatting
- **ty** — type checking
- **docpact** — docstring contract validation

Run all checks:

    ruff check --fix src/ && ruff format src/ && ty check src/ && docpact check --fix src/

### Docstring requirements

Requirements are enforced by `docpact`. View the schema for any tier:

    docpact show-schema --tier 3

**Tier assignment is automatic:**
- `_`-prefixed functions or methods on `_`-prefixed classes → Tier 1
- `@mcp.tool`, `@mcp.resource`, `@mcp.prompt` → Tier 3
- `__init__` and other dunders → inherit the class's tier
- `@property`, `@cached_property`, `@staticmethod`, `@classmethod` → inherit the class's tier
- All other public functions → Tier 2

**Tier 3 functions require all of:**
- Summary line
- `Args:` section documenting every parameter
- `Returns:` section (unless return type is None)
- `Raises:` section for all caller-observable exceptions, or `Raises:\n    None.`
- `Constraints:` section, or `Constraints:\n    None beyond type annotations.`
- `Stability:` field: one of stable, beta, internal, deprecated
- Either `MCP:` docstring section or `description=` in decorator — not both

**Constraints is for real-world conditions, not type-expressible properties.**

Belongs in Constraints:
- Scale limits, performance ceilings, resource costs
- Dependencies on external systems or shared state
- Behavioral guarantees callers may rely on
- Operational preconditions (locks, sessions, deploy ordering)
- Risk factors affecting modification decisions

Does NOT belong in Constraints — use the type system instead:
- Max length, regex, range → use `Annotated[T, ...]`
- Nullability → use `T | None`
- Enumerated values → use `Literal[...]`
- "Must be a valid X string" where X is a syntactic property

Duplication will be reported as DOC051 (deferred — see §5.3).

**Decorator and docstring MCP section are mutually exclusive.** If both are
present, `docpact` reports MCP001. Safe resolution: remove the docstring MCP
section. The decorator takes precedence.

**The `Notes:` section is for implementation rationale.** Why this approach
and not another. Specific enough that the next agent can evaluate whether
the choice remains valid.

**The `Alternatives:` section prevents repeated investigation.** If an
approach was considered and rejected, document it with the rejection reason.

**Pydantic model parameters:** document the parameter itself in `Args:`,
not its fields. Field-level documentation belongs in `Field(description=...)`
on the model definition.

### When docpact check fails

Each error includes a code, location, and description. Errors marked `[*]`
have an available fix.

1. Run `docpact check --fix src/`.
2. Resolve remaining errors.
3. Re-run `docpact check src/` to confirm.

Do not suppress with `# noqa` without a documented reason and issue reference.

### Generating stubs for new functions

    docpact generate src/tools/new_module.py

Stubs contain `[FILL]` markers. `docpact check` fails on `[FILL]` (DOC099).
Replace all markers before marking a task complete.
```

---

## 20. Code Examples

### 20.1 Tier 1 — internal function

```python
def _normalize_date_string(value: str) -> str:
    """Convert date string to ISO 8601 format."""
    ...
```

Passes. Tier 1 requires only a summary.

---

### 20.2 Tier 2 — package-public function

```python
from typing import Annotated
from annotated_types import MaxLen

def parse_filter_expression(
    expression: Annotated[str, MaxLen(4096)],
    strict: bool = False,
) -> FilterAST:
    """Parse a filter expression string into an AST.

    Args:
        expression: Filter expression in the project's filter DSL. See
            docs/filter-dsl.md for grammar specification.
        strict: When True, reject expressions using deprecated syntax.
            When False, deprecated syntax is accepted with a warning.

    Returns:
        Parsed AST ready for evaluation or further transformation.

    Raises:
        FilterSyntaxError: Expression contains syntax the parser cannot
            recover from. Message includes the position of the first
            unrecoverable token.

    Constraints:
        Parser allocations are proportional to expression depth. Adversarial
        deeply-nested input may consume significant memory; callers handling
        untrusted input should set a depth limit upstream.
        Grammar version is locked to v3. Changing the grammar is a breaking
        change for any stored filter expressions.

    Notes:
        Uses a recursive descent parser rather than a PEG parser because the
        grammar is simple enough that the added complexity of a PEG library
        is not justified. If the grammar grows beyond 20 rules, reconsider.

    Alternatives:
        lark-parser was evaluated and rejected. It adds a 40ms cold import
        penalty unacceptable for CLI use. Tracked in issue #88.
    """
    ...
```

Note: the max-length constraint lives in `Annotated[str, MaxLen(4096)]`, not in the docstring. Putting it in both is the pattern `DOC051` will catch (deferred — see §5.3).

---

### 20.3 Tier 3 — MCP-exposed tool, docstring style

```python
@mcp.tool()
def search_documents(
    query: str,
    collection: str,
    max_results: Annotated[int, Ge(1), Le(100)] = 10,
    include_metadata: bool = False,
) -> list[SearchResult]:
    """Search documents in a collection using full-text query.

    Args:
        query: Search query string. Supports boolean operators (AND, OR, NOT)
            and phrase matching with double quotes. Wildcards not supported.
        collection: Collection identifier as returned by list_collections.
            Must exist; this function does not create collections.
        max_results: Maximum number of results to return.
        include_metadata: When True, each result includes the full metadata
            dict stored at index time. Increases response size for large
            metadata payloads.

    Returns:
        List of SearchResult objects ordered by relevance score descending.
        Empty list when no documents match. Never returns None.

    Raises:
        CollectionNotFoundError: collection does not exist. Call
            list_collections to verify available collections.
        QueryError: query cannot be parsed.

    Constraints:
        Caller must hold a session with read permission on the collection.
        Permission is checked against the session established at server
        startup, not per-call.
        Query statistics logging is best-effort and non-blocking. Failure to
        log does not raise. Callers requiring guaranteed audit must log
        independently.
        Backed by an Elasticsearch cluster. Subject to cluster availability;
        500-class errors propagate as CollectionUnavailableError.

    Mutates:
        Appends to the query statistics log (non-blocking, best-effort).
        Does not modify the index or any document.

    Stability: stable

    MCP:
        Searches documents in a specified collection and returns ranked results.
        Use this tool when the user asks to find, search, or look up documents.
        Prefer this over get_document when the exact document identifier is
        not known. For listing all documents without filtering, use
        list_documents instead.

    Examples:
        >>> results = search_documents("climate change", "research-papers")
        >>> len(results) <= 10
        True
    """
    ...
```

The `max_results` range constraint lives in the type, not the docstring. The Constraints section captures operational, behavioral, and dependency information that types cannot.

---

### 20.4 Tier 3 — decorator style (equivalent)

```python
@mcp.tool(
    description=(
        "Searches documents in a specified collection and returns ranked results. "
        "Use this tool when the user asks to find, search, or look up documents. "
        "Prefer this over get_document when the exact document identifier is not "
        "known. For listing all documents without filtering, use list_documents."
    )
)
def search_documents(...) -> list[SearchResult]:
    """Search documents in a collection using full-text query.

    [Same docstring body as 20.3, without MCP: section]
    """
    ...
```

`MCP001` fires if both decorator description and docstring `MCP:` section are present.

---

### 20.5 Error output

```
src/tools/search.py:14:5: DOC012  Tier 3 function missing required section: Constraints
src/tools/search.py:14:5: DOC007  Parameter 'include_metadata' in signature but absent from Args

src/tools/search.py:14:5: MCP001  Both decorator description= and docstring MCP: section present

src/tools/legacy.py:88:1: DOC001 [*] Tier 2 function missing docstring
  = help: run --fix to insert a stub docstring

Found 5 errors (3 fixable with --fix, 1 fixable with --unsafe-fixes).
```

---

### 20.6 Pydantic model parameter

```python
from pydantic import BaseModel, Field

class SearchParams(BaseModel):
    query: str = Field(description="Search query. Supports AND, OR, NOT.")
    max_results: int = Field(
        default=10,
        description="Maximum results.",
        ge=1,
        le=100,
    )

@mcp.tool()
def search_with_params(params: SearchParams, collection: str) -> list[SearchResult]:
    """Search documents using a structured parameter object.

    Args:
        params: Search parameters. Individual fields are documented on
            SearchParams. The whole object is validated at call time.
        collection: Collection identifier as returned by list_collections.

    [remaining sections as normal]
    """
    ...
```

Field-level documentation lives on `SearchParams`. The `Args` entry documents the parameter, not the fields. `DOC050` fires if any `SearchParams` field lacks `Field(description=...)`.

---

### 20.7 Generated stub

```python
def process_payment(amount: Decimal, currency: str, idempotency_key: str) -> PaymentResult:
    """[FILL: single-sentence summary in imperative mood]

    Args:
        amount: [FILL]
        currency: [FILL]
        idempotency_key: [FILL]

    Returns:
        [FILL]

    Raises:
        [FILL]

    Constraints:
        [FILL]

    Stability: stable
    """
    ...
```

`[FILL]` markers cause `DOC099`. Generated stubs cannot pass the pipeline unmodified.

---

## 21. Open Questions

**Q1. Snapshot baseline format for semantic mode.**
The proposed `.docpact.snapshots.json` baseline approach is one of several options for managing semantic-mode prompt-version churn. Alternatives: per-error-code suppression versioning, severity downgrade on prompt version change, prompt-version-independent finding hashes. Resolution deferred until semantic mode is closer to implementation.

**Q2. `See Also` symbol resolution depth.**
Format validation in v0.1; AST symbol table resolution in v0.2. Open question: should resolution attempt to follow imports across module boundaries, or only validate intra-module references? Cross-module resolution is more useful but more expensive and more likely to produce false positives on dynamic imports.

**Q3. `__init__` and dataclass interaction. [RESOLVED]**
v0.1 treats generated dataclass `__init__` like any other `__init__`: it inherits the tier of the containing class, and Args validation applies normally. If a dataclass `__init__` has no docstring, DOC001 fires. Using the class-level docstring as the documentation source for dataclass parameters is v0.2 work — it requires deciding how class-level Args entries map to the generated `__init__` parameters, which is non-trivial.

**Q4. Rust vs. Python implementation. [RESOLVED]**
v0.1 is implemented in Python with griffe as the parsing foundation. A potential future major version may rewrite hot paths in Rust via PyO3 once Python performance ceilings are measured on real workloads. See [ADR-001](../adr/ADR-001-implementation-language.md).

---

*This document is the specification. Implementation decisions that contradict it should trigger a revision, not a workaround.*

# ADR-001: Implementation language for v0.1

**Status:** Accepted  
**Date:** 2026-05-17  
**Deciders:** [project leads]  
**Related:** Spec §5 (Scope), §7 (Architecture), §11 (Operational Modes), §13.2 (Pydantic), §13.3 (FastMCP); resolves spec §21 Q4

## Context

docpact is implementation-language-agnostic at the specification level. The architecture (parser abstraction, pure-function rule engine, deterministic structural mode) translates to any reasonable systems or scripting language. The implementation language is a separate choice with significant downstream consequences for:

- **Development velocity** — how quickly v0.1 reaches usability
- **Performance characteristics** — speed at the scales docpact will actually be invoked
- **Distribution model** — how users install and adopt the tool
- **Integration surface** — how docpact connects to the rest of the toolchain (FastMCP, Pydantic, pytest, ty)
- **Contributor accessibility** — who can realistically contribute to the codebase
- **Long-term technical positioning** — whether docpact sits alongside ruff/ty as a peer or as a separate-toolchain participant

The decision is constrained by one hard fact: docpact's primary integration targets (FastMCP, Pydantic, FastAPI, pytest) are all Python. Any implementation language must call into or interoperate with Python at some boundary. The choice is where that boundary sits.

The decision is also constrained by one operational reality discovered during research: the most attractive Rust dependency for Python parsing — Astral's `ruff_python_parser` and `ruff_python_ast` — is **not published to crates.io and has no announced plans to be published**. See [reference 1].

This ADR resolves the question: in what language should v0.1 of docpact be implemented?

## Decision

**docpact v0.1 is implemented in Python 3.12+, using `griffe` for docstring parsing and the standard-library `ast` module for Python source parsing.**

The implementation language is not part of the specification's public contract. Users interact with docpact through its CLI, its configuration files, and its output formats. A future major version may rewrite all or part of the implementation in another language (Rust via PyO3 is the most likely candidate) without breaking the user-facing contract. Such a rewrite would be subject to its own ADR.

This ADR commits only to v0.1.

## Rationale

The decision rests on four observations.

**Velocity outweighs performance at v0.1's scale.** Performance only matters if v0.1 ships. A Python implementation reaches feature-complete v0.1 in an estimated 1–3 months of focused work. A Rust implementation reaches the same milestone in an estimated 6–12 months and carries higher risk of stalling before completion. The performance ceiling of a well-engineered Python implementation (multiprocessing, content-hash caching, lazy rule evaluation) is sufficient for docpact's actual workloads: pre-commit hooks on staged files (sub-500ms), CI runs on typical codebases up to 100K LOC (under 5 seconds). The scale at which Python becomes painful — 500K+ LOC repositories or LSP-grade interactive use — is not a v0.1 target.

**griffe eliminates the largest implementation cost of a Rust port.** Docstring parsing across Google, NumPy, and Sphinx styles is non-trivial. A Rust implementation must write this parser from scratch, in v0.1 for Google and in later versions for NumPy. griffe already implements all three with sufficient quality to power mkdocstrings. Adopting griffe collapses the largest single chunk of v0.1 implementation work to zero. No equivalent crate exists in the Rust ecosystem.

**Every integration target is native.** Pydantic, FastMCP, FastAPI, pytest, and ty all operate in or through Python. A Python implementation accesses each of these directly. A Rust implementation must marshal data across an FFI boundary (PyO3 or subprocess) for every integration. This is solvable but adds permanent overhead and complexity. The Python implementation pays no integration tax.

**The performance gap is closeable without a rewrite.** When a Python implementation becomes performance-limited, the standard remediation is to identify the hot loop, rewrite it in Rust, and expose it via PyO3. This is the path taken by `orjson`, `pydantic-core`, `tokenizers`, `polars`, and many others. The same path is available to docpact if and when it is needed. The decision to start in Python is not a decision to remain in Python forever; it is a decision to defer the language-level optimization until a measurable problem exists.

## Alternatives considered

### Alternative A: Pure Rust with tree-sitter-python

**Description.** Implement docpact entirely in Rust, using `tree-sitter` and `tree-sitter-python` for source parsing and a hand-written Rust docstring parser for Google-style docstrings.

**Considered because.** Tree-sitter is published, stable, permissively licensed, and explicitly designed for the lint-and-navigate use case docpact represents. It is error-tolerant (handles partial source gracefully), provides byte ranges natively (sufficient for fix application), and has lower learning curve than ruff's AST. A Rust implementation would match the performance and distribution profile of ruff and ty, positioning docpact as a peer in that toolchain rather than as a separate ecosystem participant. Single-binary distribution via `cargo install` or platform installers is a meaningful adoption advantage.

**Not chosen because.**

1. Estimated 6–12 months of implementation work to v0.1, against 1–3 months for Python. The risk of stalling before v0.1 is real for any side-project or small-team effort.
2. Google-style docstring parsing must be implemented from scratch. NumPy and Sphinx parsers must follow for v0.2 and beyond. No equivalent of griffe exists in Rust.
3. Every integration target (Pydantic, FastMCP, pytest, ty) requires FFI marshalling. PyO3 makes this tractable but it is not free.
4. The performance argument is strong but applies only at scales docpact does not target in v0.1. Pre-commit and typical CI workloads are within Python's reach.

### Alternative B: Pure Rust with `ruff_python_parser` and `ruff_python_ast`

**Description.** Implement in Rust using Astral's parser and AST crates from the ruff project.

**Considered because.** ruff_python_parser is the most accurate, fastest, most actively maintained Python parser in Rust. It supports the latest Python syntax (3.12+), handles edge cases that tree-sitter does not, and is the same parser that powers ruff and ty. Using it would put docpact on the same parsing foundation as the toolchain it integrates with.

**Not chosen because.**

1. **The crates are not published on crates.io.** [reference 1] Astral has explicitly stated they have no plans to publish them. The only ways to depend on them are: (a) Cargo git dependency pinned to a specific revision, (b) vendoring the source into the docpact repository.
2. Git dependencies pinned to specific revisions mean every ruff update potentially introduces breaking changes that must be triaged manually. The crates have no semver guarantees. They are designed for ruff's internal needs, not for external consumers.
3. Vendoring transfers ongoing maintenance burden of a Python parser to docpact. Python language evolution (PEP 695, PEP 701, future syntax) would require keeping the vendored parser current. This is not viable for a project of docpact's scope.
4. The crates are large. ruff_python_ast alone is generated from a 1000+ line TOML schema describing dozens of node types. docpact uses approximately 5% of this surface area. Carrying the rest is permanent dead weight.
5. The crates have a stated lower bound of MSRV 1.92, raising the floor for docpact contributors.

This alternative becomes attractive if and only if Astral changes its publication policy.

### Alternative C: Pure Rust with RustPython/Parser

**Description.** Implement in Rust using the older, published RustPython/Parser crate that ruff originally forked from.

**Considered because.** It is published on crates.io and was the foundation of ruff's parsing layer through ruff v0.4.

**Not chosen because.** It is explicitly superseded by ruff_python_parser. [reference 2] Maintenance activity is low. It does not support recent Python syntax with the same fidelity. Building on a superseded foundation imports the maintenance burden of a parser without the support of an active project.

### Alternative D: Vendor Astral's crates into the docpact repository

**Description.** Copy ruff_python_parser and ruff_python_ast (MIT-licensed) into docpact and maintain a fork.

**Considered because.** It bypasses the no-publish constraint and gives docpact access to the best Rust Python parser.

**Not chosen because.** This converts docpact into a Python parser maintenance project that happens to also lint docstrings. The parser is the larger artifact. Tracking upstream changes, applying security fixes, supporting new Python syntax — these are full-time concerns for the parser project. docpact does not have the bandwidth.

### Alternative E: Hybrid — Python frontend, Rust core via PyO3, from day one

**Description.** Ship v0.1 with a Python CLI and configuration layer, but implement the rule engine and parser in Rust, bridged via PyO3.

**Considered because.** It captures the velocity benefits of Python for the user-facing layer and the performance benefits of Rust for the inner loop. This is the architecture of `pydantic-core`, `tokenizers`, `orjson`, and many other high-performance Python tools.

**Not chosen because.**

1. The premise of premature hybrid optimization. Pure-Python v0.1 has not yet been measured. Designing for a performance ceiling before knowing where the ceiling actually is risks optimizing the wrong layer.
2. PyO3 development is more demanding than either pure Python or pure Rust. Two languages, two toolchains, two test infrastructures, FFI marshalling at every boundary. v0.1 implementation time would be longer than pure Rust, not shorter than pure Python.
3. The plugin/rule API question (spec §7.5) becomes much harder. A stable plugin API across a PyO3 boundary requires stabilizing the data types that cross the boundary, which forces design decisions before usage patterns have stabilized.
4. The hybrid path remains available as a v2.0+ migration once Python implementation has revealed which specific operations are performance-critical. Choosing it now is choosing a permanent two-language architecture before any data justifies it.

## Consequences

### Positive

- v0.1 reaches a working state in weeks rather than months. The probability of a usable initial release is materially higher.
- griffe is adopted as the parsing foundation, eliminating the largest single piece of implementation work.
- Integration with Pydantic, FastMCP, pytest, ty, and other Python-ecosystem tools is native. No FFI boundary, no marshalling overhead.
- The user-facing testing module (spec §14.1) is genuinely native Python, accessible to all users without additional installation complexity.
- Contributing to docpact requires only Python. The contributor pool is larger than for Rust.
- Distribution via PyPI is straightforward. `uv tool install docpact` makes adoption frictionless.
- The implementation language is reversible. A future Rust or hybrid rewrite remains a viable optimization path.

### Negative

- The "feels like ruff" performance bar (sub-100ms for typical operations) is not reachable in v0.1. Cold-start latency from the Python interpreter is a hard floor.
- LSP-grade interactive use (sub-frame response time on every keystroke) is not feasible without a daemon mode. Daemon mode is not in v0.1.
- Distribution requires a Python interpreter present on the user's system. Standalone-binary distribution requires additional packaging work (PyOxidizer, shiv, etc.) and is not planned for v0.1.
- Very large monorepos (500K+ LOC) may see runtimes in the 10-30 second range for full scans, even with multiprocessing. This is acceptable for scheduled CI but uncomfortable for "run on every commit."
- docpact does not sit in the same binary toolchain as ruff and ty. Users running `cargo install ruff` separately install docpact via `uv tool install docpact` or `pip install docpact`. This is fine but it is not the same.

### Neutral

- The DocstringParser abstraction in spec §7.2 remains useful even in a single-language Python implementation. It isolates griffe behind a stable interface, allowing the parser to be replaced (with a Rust implementation, or with a different Python parser) without rule changes.
- The pure-function rule engine architecture (spec §7.3) is language-independent and not affected by this decision.
- The HEUR rule namespace (spec §12.3) does not depend on implementation language.

## Revisit triggers

This ADR should be reopened if any of the following occur:

1. **Astral publishes ruff_python_parser and ruff_python_ast to crates.io with semver guarantees.** This removes the most decisive operational argument against the Rust path. [reference 1] for current status.
2. **Real-world performance measurements show Python v0.1 is unusable at the scales users actually have.** Define "unusable" as: full-repository scans exceeding 30 seconds at 200K LOC on commodity CI hardware, or pre-commit scans exceeding 1 second on changed-file sets of typical PR size.
3. **LSP/IDE integration becomes a v0.x requirement.** Sub-100ms response time on edit is not reachable in cold-start Python. A daemon mode could close this gap but is itself a major architecture change.
4. **A specific hot loop is identified as the dominant cost.** This may trigger a partial hybrid migration (PyO3 for that layer) rather than a full language change. Document the migration in a follow-up ADR rather than reopening this one.
5. **griffe ceases to be actively maintained, or its API stability becomes a problem.** This would force either a vendored copy of griffe or a custom docstring parser, either of which significantly weakens the Python case.

## References

1. [Astral's stated policy on publishing ruff crates](https://github.com/astral-sh/ruff/issues/14051). "We currently have no plans to publish the crates but we could reconsider for some specific crates if someone's interested in setting up a release process." Issue #14051, with prior context in issue #10417 from 2024.
2. [RustPython/Parser supersession notice](https://github.com/RustPython/Parser). The README explicitly states the project is now superseded by ruff_python_parser.
3. [griffe project](https://mkdocstrings.github.io/griffe/). Active, well-maintained, documented. Powers mkdocstrings, which is itself widely adopted.
4. [Pydantic-core](https://github.com/pydantic/pydantic-core) as an example of the hybrid Python+Rust architecture this ADR defers to a potential future version.

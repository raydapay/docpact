# ADR-006: Interim architecture posture — per-file Python, ty as strategic target

**Status:** Accepted
**Date:** 2026-05-30
**Deciders:** Ray
**Related:** ADR-003 (per-file determinism); ADR-005 (same-file boundary; partially superseded the MCP-REG postponement); spec §8 (no-imports invariant), §13.2 (cross-module resolution open question); inbox issue #4 (parallelize file analysis)

## Context

ADR-005 drew docpact's analysis boundary at **same-file**: cross-file rules (e.g. a tool-registry entry naming a function imported from another module) were ruled out because correlating across modules needs a module graph, which docpact's "one file at a time, no imports" invariant (spec §8) deliberately forbids. PROGRESS.md left the broader question open: *"should docpact ever cross the per-file boundary at all?"*

That question forced a direction-level deliberation, because a real objection stands against the per-file boundary: **real codebases have Tier B/C imports** — `__init__` re-exports, aliases, relative and conditional imports — and tools are frequently registered centrally from many modules. A docstring/contract linter that cannot follow an import to the function it describes is blunted on its highest-value use case (central MCP-tool registries), even though its single-file core (docstring ↔ its own signature) remains fully useful.

We examined how the ecosystem resolves this:

- **ruff** stays per-file. Its linter builds a per-file semantic model and matches imported symbols by *qualified name* — it never opens the imported file. This is exactly docpact's current (and REG's) model.
- **ty** (Astral's type checker, ex–Red Knot) does real cross-file resolution, built on **Salsa** — an incremental query/dependency engine (rust-analyzer lineage) — in **Rust, no GIL**. Astral built a *new project on a new substrate* rather than bolting cross-file onto ruff. Salsa's dependency tracking is precisely what makes incremental checking sound and keeps determinism.

The measure of difficulty is that observation: correct + fast + incremental cross-file analysis is not a feature you add to a per-file Python linter; it is an architecture, and the strongest team in this space judged it needed Salsa + Rust + a fresh codebase. "Rebuild docpact on Salsa" therefore means "rewrite in Rust," and even then Salsa is the easy ~10% — the parser, semantic model, and import resolver (the Tier B/C tar pit) are the 90%, which is exactly what ty already is.

The question this ADR answers: **what is docpact's architecture direction — language, analysis scope, cross-file strategy, and parallelism — for the interim, and under what conditions do we revisit it?**

## Decision

An **interim posture**, explicitly time-bounded by the revisit triggers below:

1. **Language: stay Python.** No Rust rewrite now.
2. **Scope: stay per-file.** No module graph, no cross-file resolution. The spec §8 invariant holds. **This is gated on ty maturity (item 4), NOT on Python free-threading** — see Rationale; conflating the two is a category error.
3. **Cross-file capability: deferred entirely until ty.** No hand-rolled resolver. The griffe-backed opt-in "deep mode" (cross-file via griffe's static loader) is **deferred/rejected-for-now** — see Alternative C.
4. **Strategic target: ty.** When ty formalizes a stable public plugin / semantic-model API, docpact's preferred cross-file path is to *consume* it, not to build resolution itself. This is the north star; it is "not yet," not "no."
5. **Parallelism: implemented now, opt-in, default off.** Per-file independence makes parallel analysis sound today (issue #4). Shipped as a `jobs` setting (`--jobs` / `[tool.docpact] jobs`), default `1` (serial). The break-even between serial and parallel is a property of the *user's* project size, file complexity, core count, and OS (fork vs spawn) — **not** a property docpact can benchmark or threshold for them. So docpact ships a `docpact bench` command that measures wall-time and memory on the user's own tree and emits a copy-pasteable `jobs` recommendation. Measuring beats guessing. The dispatch is executor-abstracted so `ProcessPoolExecutor` → `ThreadPoolExecutor` is a one-line swap when free-threading lands.

Supporting principle (free insurance for item 4): **keep rule logic ruthlessly separated from the parsing/resolution substrate.** docpact already enforces this — rules are pure functions of model types; only the parser touches `ast`/griffe. Any rule reaching past the model layer is a bug. This separation is what makes a future substrate swap (own parser, ty-backed, or Rust) a contained change rather than a rewrite.

## Rationale

**Stay Python (1).** No trigger for a Rust rewrite is met: cross-file is not yet proven essential by adopters, the per-file core is fully serviceable in Python, and ty's reusable surface is not yet stable. A rewrite now would be building on shifting foundations to solve a problem we have not confirmed we must solve.

**Per-file scope is gated on ty, not free-GIL (2).** This is the seam most likely to be mis-recorded, so it is stated explicitly: the per-file-vs-cross-file decision is about **correctness, `--changed-only` soundness, and determinism**. Free-threaded Python changes none of those — it only changes *how* parallelism is implemented (threads sharing an immutable structure vs. processes pickling it). Free-threading is therefore a trigger for the *parallelism strategy* (item 5), and has nothing to do with whether we cross the file boundary. The boundary moves only when ty makes cross-file cheap and correct (item 4).

**ty is the strategic path (4).** Every honest version of "get correct cross-file" collapses toward ty: Salsa-the-framework is not the moat, the resolver + semantic model is, and Astral owns the best one. Consuming ty gets Tier-C resolution, incrementality, and speed without docpact reimplementing any of it; docpact then contributes only what is actually its own — the docstring-contract opinion (tiers, required sections, registry/MCP semantics, the agent-facing framing), which is orthogonal to type checking and unlikely to be prioritized upstream.

**Parallelism is unblocked, and the break-even is the user's to measure, not ours to guess (5).** It is sound today only because files are independent — the property a module graph would delete, which is another reason to keep cross-file out for now. The original "defer until our benchmark shows a win" framing (issue #4) was a category error: `make bench`-style numbers measure docpact's corpus on the maintainer's machine and do not generalize. The serial→parallel crossover is genuinely project- and environment-specific:

- **fork vs spawn:** on Linux/WSL2 workers fork (inherit loaded modules → cheap startup → low crossover); on macOS/Windows they spawn (re-import per worker → high startup → high crossover). Same project, different break-even by OS.
- **work, not count:** a few large, dense files parallelize better than many trivial ones.

There is not even a single break-even number per project, so any hardcoded threshold docpact picks is a guess. The honest design is therefore: **opt-in, default off** (no regression for the small-set common case, e.g. pre-commit on changed files), plus a **`docpact bench`** command that runs the user's own tree serial vs. parallel, reports median wall-time and peak memory, and prints a copy-pasteable `jobs` value — closing the measure→decide→configure loop. Memory matters as much as time: N workers ≈ N× resident memory, which can OOM a memory-capped CI container even when wall-time improves, so bench reports both. Dispatch stays **executor-abstracted** (the one place free-GIL pays off: `ProcessPoolExecutor` → `ThreadPoolExecutor` swap).

## Alternatives considered

### Alternative A: Rust + Salsa rewrite now

**Description.** Rebuild docpact in Rust on Salsa, assembling Astral's open crates (`ruff_python_parser`, `ruff_python_ast`, `ruff_python_semantic`, possibly red-knot resolver crates) plus docpact's rule logic.

**Considered because.** It is the only way to get correct cross-file + sound `--changed-only` + true parallelism + speed *simultaneously*, and Salsa's dependency tracking dissolves the soundness/determinism casualties of a module graph. Assembling Astral's crates is far more tractable than writing a type checker.

**Not chosen because.** It is a full rewrite (~2,000 statements + 896 tests) requiring standing Rust capacity, for a tool whose cross-file need is unproven. The crates it would lean on are published but **not API-stable for external consumers**; red-knot's are barely public. And it duplicates exactly what ty is building. The value it delivers *is* ty's value proposition — so the rational form of this alternative is "consume ty" (item 4), not "rebuild ty." Reserved as a future option; the rule/substrate separation (above) keeps it open at lower cost.

### Alternative B: Hand-rolled module graph in Python

**Description.** Build an intra-project import resolver + symbol index in Python to enable cross-file rules while staying in-language.

**Not chosen because.** It is the strictly-dominated middle: slow *and* a correctness tar pit. Tier B/C resolution (re-exports, aliases, relative/conditional imports) is the fiddliest part of a type checker, and misresolution reintroduces precisely the **false-positive class** that killed DOC051 and the description-similarity check (REG050). Reimplementing the hard 90% of ty, worse, in a slower language. Vetoed outright, not merely deferred.

### Alternative C: griffe-backed opt-in cross-file "deep mode"  — DEFERRED

**Description.** Keep the lean per-file `ast` path as default; add an explicitly opt-in mode that uses griffe's static loader (already proven to resolve cross-module aliases, e.g. a re-exported `search_documents` → its real signature, failing explicitly on unresolvable symbols) to run cross-file rules. Slower, global (loads the package graph), and behaviour-changing — accepted as an opt-in trade, like REG002's boundary.

**Why it was attractive.** It is the *only* path to meaningful cross-file **today** without a rewrite, and griffe's fail-explicit resolution fits docpact's "skip when unsure" discipline (literals-only DOC021, REG001).

**Why deferred / rejected-for-now.**
- **Short shelf life.** It is the first thing discarded once ty's API lands — effort spent on a throwaway.
- **Direction conflict on griffe.** The intent is to *remove* griffe from the hot path (today it is only the Google/NumPy docstring-section parser). An opt-in cross-file mode *re-introduces* griffe as a load-bearing resolver, pulling against removal. Removing griffe from the default parser and adding a griffe deep mode are two opposed projects.
- **Maintenance fork.** Two code paths, results that differ by flag, doubled test surface, and the `--changed-only`-unsound / determinism-eroded caveats resurface (in that mode only).

**Status.** Deferred, not vetoed. If cross-file becomes acutely needed by adopters *before* ty is consumable, this is the fallback to reopen — with the determinism/soundness trade documented as an experimental mode. Until then we wait.

### Alternative D: Consume ty's public API now

**Description.** Write docpact's cross-file rules against ty's semantic model / plugin API immediately.

**Not chosen because.** Timing only — ty does not yet expose a stable public plugin or semantic-model API. This is the *target* of item 4, not a present option. It becomes the chosen path the moment its precondition (a formalized, fixed ty API) is met.

## Consequences

### Positive

- The per-file core ships and stays useful, fast, and deterministic in Python with no new risk.
- `--changed-only` stays sound and results stay reproducible (both depend on per-file independence).
- Parallelism ships now as an opt-in `jobs` setting with a `docpact bench` tool, so users on large trees get the win without docpact guessing a threshold or regressing small sets.
- The strategic path is recorded with a concrete precondition, so "wait for ty" cannot quietly become "never."
- Every rejected option's why-not is on record, so revisiting is a re-read, not a re-derivation — the explicit goal of this ADR.

### Negative

- Cross-file tool-contract checking — plausibly the highest-value feature for central MCP-tool registries — remains unavailable for the interim. Adopters with cross-file registration get only same-file coverage (REG) plus REG002's boundary marker.
- docpact's reach is bounded by a decision partly outside its control (ty's roadmap).

### Neutral

- **griffe removal from the default docstring parser** — *superseded by ADR-007 (2026-05-30): griffe stays; reimplementation is not justified.* Measurement showed docstring parsing is ~3% of runtime, so the removal had no performance basis and the dependency-hygiene benefit did not outweigh the cost/risk. The `DocstringParser` Protocol keeps the decision cheaply reversible. (Originally framed here as a desired-but-unscheduled task; that framing is withdrawn.)
- The supporting separation principle is already an invariant, so adopting it formally costs nothing today.

## Revisit triggers

1. **ty formalizes a stable public plugin / semantic-model API.** Re-evaluate consuming it (Alternative D → chosen). This is the primary trigger; re-check at each ty release that touches plugins or an exposed semantic model.
2. **Cross-file tool-contract checking is proven acutely needed by real adopters** *before* trigger 1 fires. Reopen Alternative C (griffe deep mode) as a documented experimental mode.
3. **Field evidence (via `docpact bench` across real adopter projects) shows parallel is reliably beneficial above a knowable size.** Reconsider whether `jobs` should default to auto rather than off. Until then it stays opt-in.
4. **Python free-threading becomes mainstream and supported on the version floor.** Revisit the *parallelism implementation* (processes → threads, via the abstracted executor) — NOT the per-file scope.
5. **A Rust rewrite is reconsidered only if** triggers 1–2 establish cross-file as essential AND ty proves not consumable AND Rust capacity exists. Absent all three, Alternative A stays closed.

## References

1. ADR-003 — per-file, context-based determinism (the invariant this posture preserves)
2. ADR-005 — same-file tool-registry validation; the boundary this ADR generalizes into a direction
3. Spec §8 (no-imports invariant), §13.2 (cross-module resolution open question)
4. inbox issue #4 — parallelize file analysis (item 5)
5. Salsa (incremental query engine; rust-analyzer / ty foundation); ruff per-file semantic model; ty (ex–Red Knot) cross-file architecture

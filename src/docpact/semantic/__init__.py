"""Semantic analysis layer (SEM namespace) — advisory, opt-in, LLM-backed.

Unlike the `check` rules, which are deterministic and structural, semantic
analysis judges docstring *meaning* (cargo-cult restatement, an unsurfaced
precondition/constraint, an empty Returns) using an LLM. It is non-deterministic
and therefore lives behind a separate `docpact semantic` command — it never runs
inside `check` or `make verify`, so the determinism and reproducibility invariants
of `check` are untouched. See ADR-008 and spec §12.2.

The LLM is reached through the pluggable `backend.LLMBackend` protocol: one
OpenAI-compatible adapter ships (GitHub Models, OpenAI, local servers); other
providers are added as new adapter classes, not core changes.
"""

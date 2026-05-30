# ADR-008: Open the semantic layer (SEM) with a pluggable LLM backend

**Status:** Accepted
**Date:** 2026-05-30
**Deciders:** Ray
**Related:** spec §12.2 (semantic mode, designed), §15.1 (`[tool.docpact.semantic]`); ADR-006 (per-file posture — SEM does not cross it); the DOC051/REG050 deferrals (semantic content was out of scope for *deterministic* `check`)

## Context

docpact deliberately enforces **structure, not meaning** in `check`, and twice
declined a *deterministic* "is the constraint surfaced in prose" rule (DOC051,
REG050) because any heuristic for it produces false positives. The remaining way to
judge docstring *meaning* — cargo-cult restatement, a precondition/constraint implied
but not surfaced, a Returns that only restates the type — is an LLM, which the spec
already designed as **semantic mode** (§12.2): opt-in, off by default, advisory, a
separate `docpact semantic` command that never shares the `check` code path.

It stayed deferred ("no timeline") partly for lack of a usable, low-friction backend.
A spike (`scripts/spike_semantic.py`, GitHub Models, batched) settled the open
question — *is the LLM signal good enough to build on?*:

- **Precision:** 26/26 well-documented real agent tools verdict "good" — zero false
  positives on a disciplined docstring corpus.
- **Recall:** planted cargo-cult → flagged empty; planted hidden-contract → flagged
  weak with precise, actionable issues (the DOC051 *intent*, done semantically).
- **Cost:** one request, ~5k tokens, for 26 functions — trivially inside free limits.

The question this ADR answers: **open SEM, and on what backend architecture?**

## Decision

**Open the `SEM` layer**, scoped to what the spike validated, with a **pluggable LLM
backend** as the central design constraint:

1. **`docpact semantic` command** — opt-in, **advisory**, separate from `check`. It
   never runs inside `check`/`make verify` dogfood, so the determinism and
   reproducibility invariants of `check` are untouched. `SEM` is not in the default
   `select`.
2. **`SEM001` — weak/empty docstring** — the first and only finding for now: a
   docstring that adds nothing beyond the signature, or a constraint/precondition/
   side-effect implied but not surfaced. This is the DOC051/REG050 *intent* delivered
   where it belongs — in the advisory, non-deterministic layer, not in `check`.
   **DOC051 and REG050 remain reserved/deterministic; they are not revived.**
3. **Pluggable backend (`docpact.semantic.backend`).** A minimal `LLMBackend`
   protocol — `complete(system, user) -> str` — with a factory keyed on
   `[tool.docpact.semantic] backend`. Ship **one** adapter, `OpenAICompatBackend`,
   which covers GitHub Models, OpenAI, OpenRouter, Azure, and local OpenAI-compatible
   servers (Ollama, vLLM, llama.cpp) by configuring `api_base`/`model`/`api_key_env`.
   **Adding Gemini-native, Anthropic-native, or any other provider is a single new
   adapter class** behind the same protocol — no analyzer or command changes.
4. **Scoped to agent-facing functions** (`min_tier`, default 3). The spike showed the
   only false-positive source is *convention-terse* infrastructure (CLI commands,
   framework-uniform functions); SEM targets Tier-3 tools, not plumbing.
5. **Free on-ramp, BYOK to scale.** GitHub Models (`backend = "openai-compat"`,
   `api_base` = GitHub Models, `api_key_env = "GITHUB_TOKEN"`) lets an adopter assess
   for free inside their own GitHub if their data policy allows; pointing the same
   adapter at their own key/endpoint is the production path.

## Rationale

**Why a backend protocol, not a hardcoded client.** Adopters' constraints differ:
some can only send code to a self-hosted model (data governance), some standardize on
Gemini or Claude, some want the free GitHub on-ramp. The variability is entirely in
*how you call the model*; the analyzer (collect → batch → prompt → parse findings) is
backend-agnostic. Isolating the call behind `complete(system, user) -> str` means the
expensive, stable part (prompts, batching, finding shapes) is written once, and
supporting a new provider is an adapter, not a fork. One OpenAI-compatible adapter
already covers most of the market; native Gemini/Anthropic are additive.

**Why advisory and separate from `check`.** LLM output is non-deterministic across
model versions even at temperature 0 — it cannot back a deterministic gate without
violating the reproducibility invariant (ADR-003, spec). So SEM is its own command,
findings are advisory, and `check`/dogfood are untouched. This is exactly the spec's
§12.2 design; this ADR activates it rather than redesigning it.

**Why this doesn't reopen DOC051.** DOC051/REG050 were declined as *deterministic*
`check` rules because a heuristic for "constraint surfaced in prose" false-positives.
SEM001 does the same job in the layer where non-determinism is acceptable and the
detector is an LLM, not a substring match. The deterministic codes stay reserved so
the boundary ("`check` is structure; `semantic` is meaning") is crisp.

## Alternatives considered

### Alternative A: hardcode an OpenAI client

Simpler short-term. **Rejected:** it forecloses local-model and other-provider
adopters (the data-governance case is real), and a provider swap would touch the
analyzer. The protocol costs ~10 lines and removes that coupling — Ray's explicit
requirement.

### Alternative B: keep SEM deferred; ship constraint-surfacing as an opt-in heuristic

The DOC051 heuristic, default-off. **Rejected:** the spike showed the LLM does the job
with far better precision/recall than any substring heuristic, and a heuristic in
`check` still muddies the deterministic boundary. The LLM in an advisory layer is the
cleaner answer.

### Alternative C: run SEM inside `check`

**Rejected:** breaks determinism/reproducibility and would make `make verify`
non-deterministic and network-dependent. SEM must be a separate, opt-in command.

## Consequences

### Positive

- Delivers the meaning-level check (cargo-cult, hidden contract) that `check`
  structurally cannot — validated by the spike.
- Backend-pluggable: GitHub Models / OpenAI / local / future Gemini-Anthropic via one
  adapter each, no core changes.
- `check`'s determinism, reproducibility, and zero-network guarantees are intact (SEM
  is a separate command, off by default).
- Gives adopters a free, in-GitHub way to assess; BYOK to scale.

### Negative

- A new subsystem to maintain (command, analyzer, backend, config), plus a runtime
  dependency-free HTTP path (stdlib `urllib`) we own.
- Findings are non-deterministic and advisory — cannot gate deterministically; users
  must understand this.
- Sends docstring/signature text to an external (or self-hosted) model — a
  data-governance decision the adopter opts into.

### Neutral

- `[tool.docpact.semantic]` config shape follows the spec §15.1 design.
- SEM001 is registered (visible in `list-rules`) but never fires in `check`.

## Revisit triggers

1. **A second backend is requested** (Gemini/Anthropic-native, or a non-OpenAI local
   shape) → add an adapter class; the protocol should need no change. If it does, the
   protocol was wrong — revisit it.
2. **Findings prove noisy in the field** → tighten scope/prompt, or add
   `finding_threshold`/`sample_rate` (spec-designed, not yet built).
3. **A deterministic structured-constraint detector becomes feasible** → DOC051 could
   still ship in `check` for the narrow type-expressible cases, complementing SEM.

## References

1. spec §12.2 (semantic mode design — this ADR activates it), §15.1 (`[tool.docpact.semantic]`)
2. `scripts/spike_semantic.py` — the evaluation that cleared the bar
3. ADR-003 (determinism — why SEM is advisory/separate); ADR-006 (per-file posture — SEM does not cross it)
4. PROGRESS.md "Deferred with reasoning" — DOC051 (stays reserved/deterministic)

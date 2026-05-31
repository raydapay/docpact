# Adopting docpact

This guide is for teams integrating docpact into an existing Python repository.
It covers installation, CI setup, per-project configuration, and how to get
real value out of the tool — including what docpact enforces and what it
deliberately does not.

---

## Installation

Not yet published to PyPI — install from the repository:

```bash
uv add --dev "docpact @ git+https://github.com/raydapay/docpact.git"
# or
pip install "git+https://github.com/raydapay/docpact.git"
```

Requires Python 3.11+.

---

## Minimal configuration

Add to `pyproject.toml`:

```toml
[tool.docpact]
schema = "1"
format = "google"   # or "numpy" for NumPy-style docstrings
select = ["DOC", "MCP"]
```

Run the linter:

```bash
uv run docpact check src/
```

---

## CI integration

```yaml
# .github/workflows/ci.yml
- name: docpact
  run: uv run docpact check src/
```

Or add it to your `Makefile`:

```makefile
lint:
    ruff check src/
    docpact check src/
```

### Scheduled semantic check (advisory, secretless)

`docpact semantic` is **advisory and non-deterministic**, so it does not belong in
the blocking `check` job — run it on a schedule and read the report. The built-in
`GITHUB_TOKEN` can call GitHub Models directly when the workflow grants
`models: read`, so there is **no PAT or secret to manage**:

```yaml
# .github/workflows/semantic.yml
name: docpact semantic
on:
  schedule:
    - cron: "0 6 * * 1"   # Mondays 06:00 UTC
  workflow_dispatch: {}    # also runnable on demand

permissions:
  contents: read
  models: read             # lets GITHUB_TOKEN call GitHub Models — no secret needed

jobs:
  semantic:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - name: Semantic docstring review (advisory)
        env:
          GITHUB_TOKEN: ${{ github.token }}
        run: uv run docpact semantic src/ --exit-zero >> "$GITHUB_STEP_SUMMARY"
```

with the matching config:

```toml
[tool.docpact.semantic]
backend = "openai-compat"
model = "openai/gpt-4o-mini"
api_base = "https://models.github.ai/inference"
api_key_env = "GITHUB_TOKEN"     # the workflow sets this from github.token
# min_tier = 3                   # scope to agent-facing tools (default)
```

`--exit-zero` keeps the job green — findings are a report (in the run's **Summary**),
not a gate. Notes: it sends docstring/signature text to GitHub Models (GitHub's own
service); free-tier limits are ample for a weekly batched run; to use a different
provider or your own key, point `api_base`/`api_key_env` at it (the backend is
pluggable — see ADR-008).

---

## Cross-file checks (`--crossfile`, opt-in)

If your tools register **imported** symbols — a Pydantic model as `input_model`,
a function as `handler` — the cross-file `REG` rules keep their contracts honest:
`REG010` checks the documented `Args:` against the imported model's fields (a
field added but never documented, or a documented arg that no longer exists);
`REG011` checks that the imported handler's signature actually accepts the
parameters the tool declares. A registered imported handler is also held to the
Tier-3 documentation bar in its own file. This is the cross-file complement to
the same-file `REG` rules, and the declarative replacement for hand-written
"tool contract" tests.

It is **deterministic** (unlike `docpact semantic`), so it *can* gate CI — but it
needs a language server to resolve imports, so it is off by default and runs only
under `--crossfile`:

```bash
# install the bundled default server (ty), or use one you already have
uv add "docpact[crossfile] @ git+https://github.com/raydapay/docpact.git"

docpact check src/ --crossfile        # REG must also be in `select`
```

```toml
[tool.docpact]
select = ["DOC", "REG"]               # REG010 needs the REG namespace enabled

[tool.docpact.lsp]
server = ["ty", "server"]             # swappable: ["pyright-langserver", "--stdio"], ["pylsp"], …
# timeout = 15.0                       # per-request / definition readiness budget (seconds)
```

Notes and caveats:

- **Opt-in, doesn't touch the default `check`.** Without `--crossfile`, `check`
  stays per-file, offline, and dependency-free.
- **Graceful degradation.** A missing or failing server prints a clear note and
  the run continues with the per-file results — it never crashes the build.
- **Server-swappable, no lock-in.** `docpact` speaks the protocol, not a vendor;
  change one config line to switch servers. See [ADR-009](docs/adr/ADR-009-cross-file-via-lsp.md).
- **Heavier than per-file.** Per-symbol queries plus workspace indexing make it a
  better fit for a dedicated CI step than a pre-commit hook on every save.
- **Static.** The server resolves without executing your code; `docpact` still
  never imports it.

A blocking CI step looks like a normal `check` with the flag, once `docpact` is
installed with the `crossfile` extra (so a language server is on `PATH`):

```yaml
# with docpact[crossfile] in your dev dependencies, ty is pulled in by uv sync
- run: uv sync
- run: uv run docpact check src/ --crossfile
```

---

## Pre-commit integration

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: docpact
        name: docpact
        language: system
        entry: uv run docpact check
        types: [python]
        pass_filenames: true
```

---

## What docpact checks

| Rule | What it catches | Default severity |
|------|----------------|-----------------|
| DOC001 | Function missing a docstring entirely | ERROR |
| DOC002 | Module missing a module-level docstring (`__init__.py` excluded by default) | WARNING |
| DOC003 | Class missing a docstring | WARNING |
| DOC007 | Args section doesn't match the function signature | ERROR |
| DOC012 | Required section absent for the function's tier | ERROR |
| DOC013 | Empty section not in canonical form (fixable) | WARNING |
| DOC014 | Suspicious parameter name (likely typo of a real parameter) | WARNING |
| DOC021 | `Defaults to X` prose doesn't match the signature default | WARNING |
| DOC022 | Typed prose annotation doesn't match the signature type | WARNING |
| DOC050 | Pydantic model field missing `Field(description=...)` | WARNING |
| DOC052 | `Examples` section absent (only when `require_examples_min_tier` is set; fixable) | ERROR |
| DOC099 | `[FILL]` stub marker not replaced | ERROR |
| MCP001 | Decorator `description=` and docstring `MCP:` section both present | WARNING |
| TY001 | Returns section has content but the return annotation is `None` | ERROR |
| TY002 | Returns section is `None.` but the return annotation is non-`None` | WARNING |
| PARSE001 | File has a Python syntax error and cannot be parsed | ERROR |
| FIX001 | Bare `# nodo` without codes or reason | WARNING |
| FIX002 | Suppression names codes but has no `-- reason` | WARNING |
| FIX003 | Suppression names a code with no active violation on that line | WARNING |
| FIX004 | Suppression comment not on the `def` line (silently ignored) | WARNING |
| REG001 | Tool-registry schema names a parameter absent from the signature | ERROR |
| REG002 | Tool-registry entry names no function in the same file | OFF (opt-in) |

`DOC051` (Constraints duplicates Annotated metadata) is reserved but deferred — not
yet active.

The `DOC`, `MCP`, and `PARSE` namespaces are enabled by default. `FIX` (suppression
hygiene), `TY` (type/docstring coherence), and `REG` (same-file tool-registry
cross-checks) are opt-in:

```toml
select = ["DOC", "MCP", "PARSE", "FIX", "TY", "REG"]
```

---

## Tier system

docpact assigns each function to a tier that determines which documentation
sections are required. Assignment is automatic and deterministic:

| Tier | What it matches | Required sections |
|------|----------------|-------------------|
| 1 | `_` prefixed (internal) | Summary only |
| 2 | Public function, not MCP-decorated | Summary + Args + Returns |
| 3 | `@mcp.tool`, `@mcp.resource`, `@mcp.prompt` | Summary + Args + Returns + Raises + Constraints + Stability |
| 4 | Explicitly configured in `tiers` table | As configured |

Tier 4 allows opt-in to Tier 3 strictness without MCP decorators:

```toml
[tool.docpact.per-file-tier]
"src/api/handlers.py" = 3
```

---

## Recommended posture for MCP / agent-tool surfaces

If your codebase exposes tools to an LLM, the docstring *is* the contract the agent
reads to decide what to call and how — so hold those functions to the strictest tier
and the highest-signal sections. A posture that matches what teams enforce in
practice:

```toml
[tool.docpact]
select = ["DOC", "MCP", "REG"]   # REG only if you use a same-file tool registry
require_examples_min_tier = 3    # DOC052: Examples is the highest-signal section
                                 # for a tool-calling agent — require it on Tier 3 tools

[tool.docpact.pydantic]
undescribed_fields = "error"     # DOC050: every Pydantic input-model field needs a description
```

Get tools onto Tier 3 by `@mcp.tool` (automatic), a same-file `ToolDefinition`
registry (the `REG` Tier-3 floor), or `per-file-tier = 3` on the tools module.

**Two honest limits**, both consequences of docpact being a *static, per-file* linter
(see ADR-006):

- **DOC012/DOC052 read the function's own docstring.** If your tool's human-facing
  description lives in a separate `description="..."` string passed to a registration
  (not the function docstring), those rules check the function, not that string.
  Put the contract on the function, or that description won't be linted.
- **Cross-file parity is not checked.** Whether a tool's documented `Args` match an
  *imported* Pydantic input model, or constraints (`ge=`, `Literal[...]`) are surfaced
  in prose, is correlation across modules — out of scope until docpact can consume
  ty (ADR-006). Keep that in a project-local contract test for now. docpact covers the
  per-file pieces: field descriptions present (DOC050), a required Examples block
  (DOC052), and the function's own docstring↔signature parity (DOC007/DOC012).

For *meaning* (is a tool docstring actually informative, or cargo-cult? does it surface
its preconditions?), there's an opt-in, advisory `docpact semantic` (SEM001) — an
LLM-backed check, separate from `check`, with a pluggable backend (GitHub Models is a
free on-ramp). It's non-deterministic, so it never gates `check`. See the README's
"Semantic mode" section and ADR-008.

---

## Tuning for your repo

### Suppress noisy rules at file level

```toml
[tool.docpact.per-file-ignores]
# Generated protobuf stubs — no point documenting these.
"src/proto/**/*.py" = ["DOC001", "DOC002"]
```

Patterns are anchored to the directory containing `pyproject.toml`. Write them as paths relative to the project root — they match correctly regardless of where `docpact check` is invoked from.

Note: `__init__.py` files are already excluded by DOC002's default behaviour.
Additional exclusions (generated code, stubs, migration scripts) use
`per-file-ignores` as shown above.

### Silence specific checks globally

```toml
[tool.docpact]
ignore = ["DOC013"]  # empty sections OK in this repo
```

### Raise severity for critical paths

```toml
[tool.docpact.rules]
DOC007 = "error"
DOC012 = "error"
```

### Exclude paths entirely

```toml
[tool.docpact]
exclude = ["tests/", "scripts/", "migrations/"]
```

---

## Inline suppression

Suppress a rule on a specific function:

```python
def legacy_function(  # nodo: DOC001 -- pre-docpact, scheduled for cleanup in #412
    x: int,
) -> None:
    pass
```

**The suppression must be on the `def` keyword line** — not on the closing
`) -> None:` line. When ruff's formatter wraps a long signature, it moves
trailing comments to the `) -> None:` line, which silently breaks suppression
(docpact matches on `func.line`, the `def` keyword line). Placing the comment
after the opening paren — `def foo(  # nodo:` — survives formatting.

The bare form (`# nodo` without codes) fires FIX001 when that rule is enabled,
because it is opaque to reviewers. Always name the code and include a reason.

The suppression marker is configurable. Default: `nodo`. To support a migration
from `# noqa`:

```toml
[tool.docpact]
suppress_comment = ["nodo", "noqa"]
```

---

## What docpact does NOT check

**Content quality.** A docstring that passes every rule is not necessarily useful.
The following passes all checks:

```python
def process(user_id: str, flags: int) -> dict:
    """Process.

    Args:
        user_id: The user id.
        flags: The flags.

    Returns:
        The result.
    """
```

Every field restates the parameter name. A coding agent reading this learns
nothing beyond what the type annotations already say.

Useful docstrings describe the *why* and the *contract*, not the *what*:

```python
def process(user_id: str, flags: int) -> dict:
    """Apply pending transforms to a user account.

    Args:
        user_id: UUID of the user record. Must exist in the user table;
            raises ValueError if not found.
        flags: Bitmask of FeatureFlag values. Unknown bits are silently
            ignored for forward compatibility.

    Returns:
        Snapshot of the account state after all transforms applied,
        keyed by field name. Callers can diff against the prior snapshot
        to determine what changed.
    """
```

docpact builds the scaffold and enforces its presence. Filling that scaffold
with signal is the author's (or agent's) responsibility.

---

## For coding agents: what to put in AGENTS.md / CLAUDE.md

If your team uses coding agents (Claude Code, Cursor, Copilot Workspace, etc.),
add this to your `CLAUDE.md` or `AGENTS.md`:

```markdown
## Docstring requirements

This repo uses docpact to enforce docstring contracts. Run `docpact check src/`
before committing. Violations are CI failures.

Key rules:
- Every public function needs a docstring (DOC001).
- Every module needs a module-level docstring (DOC002).
- Args section must match the signature exactly (DOC007).
- Tier 3 functions (@mcp.tool, @mcp.resource, @mcp.prompt) require Args,
  Returns, Raises, Constraints, and Stability sections (DOC012).

**Content quality matters.** A docstring that passes all checks is not
automatically useful. Avoid restating the parameter name:

    user_id: The user id.      ← noise, not signal

Write what the signature cannot express: preconditions, side effects,
invariants, what failure looks like, what the return value actually means.

    user_id: UUID of the user record. Must exist; raises ValueError if not.

When docpact's --fix inserts a stub with [FILL] markers (DOC099), that is
the trigger to write real content. Do not replace [FILL] with restatements.
```

---

## Generating stubs

To insert a docstring stub for functions that lack one:

```bash
docpact check src/ --fix
```

This writes the stub and leaves `[FILL]` markers. DOC099 then fires on any
stub not yet replaced, keeping the pipeline from silently passing unfilled
stubs.

For a dry run (shows the diff without writing):

```bash
docpact check src/ --diff
```

---

## Listing rules

```bash
docpact list-rules
```

Shows all registered rules with their code, namespace, summary, severity,
and fix availability.

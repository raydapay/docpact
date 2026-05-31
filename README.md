# docpact

**ruff checks your code. ty checks your types. Nothing checks your docstrings.**

---

Until now.

Coding agents, MCP tools, and LLM clients read docstrings to decide what to call and how to call it. When the code changes and the docstring doesn't, they're working from a lie. A renamed parameter sends them to the wrong argument. A missing `Constraints` section leaves out the preconditions they need to call safely. The drift is invisible in review and silent at runtime — until something breaks in a way that's hard to trace.

`docpact` is a CI-first structural linter for Python docstrings. It enforces docstring contracts the same way ruff enforces style and ty enforces types: as a gate that fails fast on drift.

```
$ docpact check src/

src/tools/payments.py:34:0: DOC007 Documented parameter 'amount' not in signature
  = help: Rename or remove the 'amount' entry in Args
src/tools/users.py:12:0: DOC012 Tier 3 function missing required section: Constraints
src/tools/users.py:12:0: DOC012 Tier 3 function missing required section: Stability
src/tools/notify.py:88:0: TY001 Return annotation is 'None' but Returns section documents a value

Found 4 errors. Run 'docpact check src/ --fix' to apply 1 safe fix.
hint: to suppress a violation: # nodo: CODE -- reason  (or --add-suppression to baseline all)
```

The first error: `payments.py` was refactored from `amount` to `amount_cents` six weeks ago. The docstring wasn't updated. Every agent calling that tool has been generating broken payloads ever since.

---

## Install

```bash
pip install git+https://github.com/raydapay/docpact.git
# or
uv add git+https://github.com/raydapay/docpact.git

# with the optional cross-file analysis extra (bundles a default LSP server)
uv add "docpact[crossfile] @ git+https://github.com/raydapay/docpact.git"
```

## Usage

```bash
docpact check src/                    # check all .py files under src/
docpact check src/ --fix              # apply safe fixes in-place
docpact check src/ --diff             # preview fixes as a unified diff
docpact check src/ --format sarif     # SARIF 2.1.0 for GitHub Code Scanning
docpact check src/ --format json      # machine-readable JSON
docpact check src/ --add-suppression  # baseline: add # nodo: comments for all current violations
docpact check src/ --config /path/to/pyproject.toml  # explicit config path (bypasses CWD discovery)
docpact check src/ --jobs 0           # parallel analysis across all cores (0=auto, 1=serial default)
docpact generate src/                 # insert stub docstrings for undocumented functions
docpact list-rules                    # list all rules with severity and fixability
docpact bench src/                    # measure serial vs parallel on your tree; recommends a jobs value
docpact semantic src/ --dry-run       # LLM-backed meaning check (advisory); --dry-run shows prompts, no API call
docpact check src/ --crossfile        # opt-in cross-file rules (REG010/REG011) via an LSP server
```

### Semantic mode (`docpact semantic`)

Opt-in, advisory, and separate from `check` (so `check` stays deterministic and
offline). It uses an LLM to flag what structure can't — cargo-cult docstrings, a
precondition/constraint implied but not surfaced, an empty Returns. Configure a
backend under `[tool.docpact.semantic]`; the LLM layer is pluggable
(OpenAI-compatible ships — GitHub Models, OpenAI, local Ollama/vLLM — and other
providers are added as adapters). `--dry-run` prints the exact prompts and sends
nothing. See [ADR-008](docs/adr/ADR-008-open-semantic-layer.md).

### Cross-file mode (`--crossfile`)

Opt-in, and off by default — the standard `check` is per-file, offline, and
fast. `--crossfile` runs the cross-file `REG` rules against tool-registry entries
that reference **imported** symbols:

- **REG010** — a tool's documented `Args:` is out of parity with its imported
  `input_model` fields (a model field the docs omit, or a documented arg with no
  matching field).
- **REG011** — a parameter the tool declares (its JSON schema, or its imported
  `input_model` fields) is not accepted by its imported `handler`'s signature —
  the cross-file analogue of REG001.

```python
# schemas.py
class SearchInput(BaseModel):
    query: str
    limit: int

# tools.py  — registers an imported model + handler
from schemas import SearchInput
from handlers import search_cases          # def search_cases(query: str) -> list

TOOLS = [ToolDefinition(name="search", input_model=SearchInput, handler=search_cases,
                        description="Search.\n\nArgs:\n    query: Text to match.")]
```

```
$ docpact check . --crossfile
tools.py:6:8: REG010 input model 'SearchInput' field 'limit' is not documented in tool 'search' Args section
tools.py:6:8: REG011 tool 'search' input model declares parameter 'limit', which imported handler 'search_cases' does not accept
```

The model gained a `limit` field; neither the tool's `Args:` nor the handler caught up.

It also applies a **cross-file Tier-3 floor**: a function registered as an
imported handler is held to the agent-facing documentation bar in its own file,
and `docpact semantic --crossfile` reviews it (and feeds the imported model's
fields into the prompt). See [ADR-010](docs/adr/ADR-010-cross-file-tier-floor-and-semantic.md).

Resolution is delegated to a language server over the standard Language Server
Protocol — `docpact` asks it to resolve the imported symbol to its defining
file, then does its own AST extraction (it never imports or executes your code).
The server is **swappable**: ty is the default, but any LSP-conformant server
(pyright, pylsp) works via `[tool.docpact.lsp] server`. Install the bundled
default with the `crossfile` extra, or point at a server you already have.

It runs only when both `REG` is in `select` and `--crossfile` is passed; a
missing or failing server degrades gracefully (a clear note, the run continues).
Per-symbol LSP queries plus workspace indexing make it heavier than the per-file
pass — fitting for an opt-in CI step, not every keystroke. Measure the added cost
on your own tree with `docpact bench --crossfile`. The LSP resolution is serial
(one session), but the per-file analysis still parallelizes (`--jobs`).
Deterministic with a pinned server. See [ADR-009](docs/adr/ADR-009-cross-file-via-lsp.md).

## What it checks

| Namespace | Rules | What |
|---|---|---|
| `DOC` | DOC001–DOC003, DOC007, DOC012–DOC014, DOC021–DOC022, DOC050, DOC052, DOC099 | Structural completeness: missing docstrings, missing sections, parameter mismatch, default drift, type/prose mismatch, Pydantic field descriptions, required Examples (when configured), stale `[FILL]` markers |
| `TY` | TY001–TY002 | Type/docstring coherence: `-> None` with substantive Returns prose; non-None return with empty Returns |
| `MCP` | MCP001 | MCP-specific conflicts: decorator `description=` duplicates docstring `MCP:` section |
| `FIX` | FIX001–FIX004 | Suppression hygiene: bare suppression comments, missing `-- reason`, stale suppressions, misplaced suppression comments |
| `PARSE` | PARSE001 | Parse-time errors: file contains a Python syntax error and cannot be checked; fires before all other rules |
| `REG` *(opt-in)* | REG001–REG002 | Tool-registry consistency: a same-file `ToolDefinition`/dict registry whose JSON-Schema parameter is absent from the function signature. Add `REG` to `select` to enable. |
| `REG` *(opt-in, cross-file)* | REG010, REG011 | Cross-file: a tool entry's documented `Args:` out of parity with its **imported** `input_model` fields (REG010), or a declared parameter the **imported** `handler` does not accept (REG011). Resolved via an LSP server; run only under `docpact check --crossfile`. See below. |
| `SEM` *(opt-in, advisory)* | SEM001 | Meaning, not structure: LLM-judged cargo-cult restatement, an unsurfaced precondition/constraint, an empty Returns. Run via `docpact semantic` — never part of `check`; non-deterministic and advisory. |

Full rule documentation: [`docs/rules/`](docs/rules/).

## Tier model

Not every function needs the same documentation depth. An internal helper needs a summary. An MCP tool needs `Constraints`, `Stability`, and `MCP` sections — because the agent calling it needs that context to call safely.

`docpact` assigns tiers automatically from decorators and file structure:

| Tier | Audience | Required sections |
|---|---|---|
| 1 | Internal | Summary |
| 2 | Package-public API | Summary, Args (when params present), Returns (when non-None) |
| 3 | MCP-exposed tools | Tier 2 + Raises, Constraints, Stability, MCP |
| 4 | FastAPI routes via FastMCP | Same as Tier 3 — use explicit `per-file-tier` config; auto-detection not yet shipped |

Most projects need no tier config. When automatic assignment doesn't fit — for example, a project using a custom MCP registry instead of `@mcp.tool` decorators — override per file:

```toml
[tool.docpact.per-file-tier]
"src/domain/mcp/tools/*.py" = 3
"src/routes/*.py" = 4
```

Patterns are anchored to the directory containing `pyproject.toml`. `src/domain/mcp/tools/*.py` matches files relative to the project root, so it works regardless of where `docpact check` is invoked from.

If the custom registry is a same-file `list[ToolDefinition]` (or list of `{"name", "description", "parameters"}` dicts), enabling the `REG` namespace is more precise than a glob: functions named by a registry entry are automatically held to a Tier 3 floor — only the registered functions, not every function in the file. See the `[tool.docpact.registry]` config below.

## Adopting in an existing codebase

A codebase with hundreds of existing violations can't add `docpact` to CI cleanly without first silencing the backlog. The `--add-suppression` flag does this in one step:

```bash
docpact check src/ --add-suppression
```

This adds `# nodo: CODE -- baseline` to every `def` or `class` line that currently has a violation. On the next run, those lines are suppressed; only new violations fail the build. Work off the backlog by removing suppression comments as you write the missing docstrings.

Preview what will be added before committing:

```bash
docpact check src/ --add-suppression --diff
```

Use a custom reason to link to a tracking issue:

```bash
docpact check src/ --add-suppression --suppression-reason "pre-docpact backlog, see #512"
```

## Configuration

```toml
[tool.docpact]
schema = "1"
format = "google"                # or "numpy"
select = ["DOC", "MCP", "FIX", "TY"]
suppress_comment = ["nodo"]      # inline suppression marker
jobs = 1                         # parallel workers; 1 = serial (default), 0 = all cores

[tool.docpact.per-file-ignores]
"src/generated/*" = ["DOC"]

# Opt-in: cross-check same-file tool registries (REG namespace). Add "REG" to select.
[tool.docpact.registry]
tool_definition_class = ["ToolDefinition"]   # constructor name(s); flat dict literals also recognized
# assign_tier = true                         # registry membership → Tier 3 floor (default)
# no_tier_floor = ["src/legacy/**"]          # files where the floor is not applied

# Opt-in: advisory LLM semantic check (`docpact semantic`). Pluggable backend.
[tool.docpact.semantic]
backend = "openai-compat"                    # OpenAI-compatible: GitHub Models, OpenAI, Ollama, vLLM…
model = "openai/gpt-4o-mini"
api_base = "https://models.github.ai/inference"   # e.g. GitHub Models (free to try)
api_key_env = "GITHUB_TOKEN"                 # name of the env var holding the key — never the key
# min_tier = 3                               # scope to agent-facing tools (default 3)

# Opt-in: cross-file analysis (REG010) via an LSP server. Used only by `check --crossfile`.
[tool.docpact.lsp]
server = ["ty", "server"]                    # any LSP-conformant server: ["pyright-langserver", "--stdio"], …
# timeout = 15.0                             # seconds per request / definition readiness budget
```

Inline suppression goes on the `def` keyword line:

```python
def build_internal_graph(  # nodo: DOC012 -- internal; tier override not yet wired
    nodes: list[str],
) -> Graph: ...
```

> **ruff formatter note:** ruff moves trailing comments on a wrapped signature's `def` line to the
> closing `) -> ReturnType:` line. A suppression comment there will not fire — docpact matches on the
> `def` line. Put the comment after the opening `(` as shown above; ruff leaves it there.

When you hit a violation and want to suppress it, the error output shows the syntax — no need to look it up.

## CI integration

**GitHub Actions with Code Scanning:**

```yaml
- name: docpact
  run: docpact check src/ --format sarif --exit-zero > docpact.sarif

- name: Upload SARIF
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: docpact.sarif
```

**pre-commit:**

```yaml
repos:
  - repo: https://github.com/raydapay/docpact
    rev: v0.1.0a8
    hooks:
      - id: docpact
```

## Boundaries

`docpact` checks structure, not meaning. A docstring that passes every check is not necessarily a good docstring. It is a *consistent* one: the Args match the signature, the required sections are present, the types don't contradict the prose. Content quality — whether the description is actually useful — is the author's responsibility.

It does not replace ruff or ty, and it never imports or executes the code it analyzes — all analysis is static (the optional cross-file mode resolves imports through a language server, which also resolves statically). Deterministic structural checks are the default; the opt-in `docpact semantic` mode adds advisory, LLM-judged *meaning* checks as a separate, non-blocking command.

## Platform support

CI runs on **Linux** (Python 3.11, 3.12, 3.13) and **Windows** (Python 3.11);
both run the full non-mutating gate (lint, types, tests, coverage, dogfood).
**macOS** is developed and tested locally but is not in CI. Glob patterns
(`per-file-tier`, `per-file-ignores`, `exclude`) are normalized with `as_posix()`,
so `/`-separated patterns match correctly on Windows.

One platform caveat: `docpact bench` reports peak memory via `getrusage`, which is
Unix-only — on Windows it reports timings and shows memory as `—`.

## Status

Self-hosting: `docpact` validates its own source on every commit. 1006 tests, 94% coverage.

Active rules: DOC001–DOC003, DOC007, DOC012–DOC014, DOC021–DOC022, DOC050, DOC052, DOC099, MCP001, FIX001–FIX004, TY001–TY002, PARSE001, REG001–REG002, SEM001 (advisory).

## Documentation

| Document | Purpose |
|---|---|
| [Specification](docs/spec/docpact-spec.md) | Full design specification. Source of truth for what docpact is and why. |
| [Rule docs](docs/rules/) | One page per rule: what it checks, examples, configuration. |
| [ADR index](docs/adr/README.md) | Architecture decision records. Why each significant choice was made. |
| [Progress](docs/PROGRESS.md) | Milestone log and v0.2 scope. |

## License

MIT. See [LICENSE](LICENSE).

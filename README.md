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

## Status & versioning

docpact is **alpha**: usable and self-hosting, but pre-1.0 — rule codes, config
keys, and the spec may still change in response to adopter feedback. It is
installed from git and is not yet published to PyPI.

Two independent counters appear in the docs; don't conflate them:

- **Release version** (`0.1.0aN`) — the actual package version, a pre-1.0 alpha
  line. This is the only number that means "a release."
- **Spec cycles** (`0.1`, `0.2`, `0.3`) — *development milestones* tracking which
  slice of the [specification](docs/spec/docpact-spec.md) is built. "Spec cycle
  0.3 complete" describes scope delivered, not a release.

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
docpact bench src/ --crossfile        # also measure the cross-file pre-pass cost (startup vs query time)
docpact semantic src/ --dry-run       # LLM-backed meaning check (advisory); --dry-run shows prompts, no API call
docpact semantic src/ --changed-only origin/main  # scope the meaning check to a PR's changed files
docpact semantic src/ --scan-modes module          # SEM002: weak module docstrings (gpt-4o-class model only!)
docpact check src/ --crossfile        # opt-in cross-file rules (REG010/REG011) via an LSP server
```

### Semantic mode (`docpact semantic`)

Opt-in, advisory, and separate from `check` (so `check` stays deterministic and
offline). It uses an LLM to flag what structure can't — cargo-cult docstrings, a
precondition/constraint implied but not surfaced, an empty Returns. Configure a
backend under `[tool.docpact.semantic]`; the LLM layer is pluggable
(OpenAI-compatible ships — GitHub Models, OpenAI, Gemini via its
OpenAI-compatible endpoint, local Ollama/vLLM — and other providers are added as
adapters). `--dry-run` prints the exact prompts and sends nothing. Quality
scales with the model — `gpt-4o-mini` (the free GitHub Models on-ramp) is the
floor and has a higher false-positive rate; a stronger model has fewer.

`--changed-only <ref>` scopes the scan to files a PR touched (the cheapest cost
control); `finding_threshold` under `[tool.docpact.semantic]` tunes noise —
`"weak"` (default) surfaces weak and empty docstrings, `"empty"` only the
wholly-vacuous ones.

**Advisory by default; gating is your call.** SEM is **never part of `check`**, so
the deterministic gate stays offline and reproducible. A team that *wants* SEM to
gate runs `docpact semantic` as its own CI step (it exits non-zero on findings
unless `--exit-zero`) and tunes noise with `finding_threshold` + the `SEM001`
severity. docpact takes no stance on whether you should — advisory by default,
configurable if you want more. See
[ADR-008](docs/adr/ADR-008-open-semantic-layer.md).

**Stable intent, not stable behavior.** Unlike the deterministic codes, a SEM
code's behavior tracks the model and the prompt, neither fully pinned by the code
(the model is an external target; the prompt is docpact source we may revise).
SEM therefore guarantees *what it looks for*, not byte-identical findings across
model or prompt changes. So every run records its provenance — `model=<id>` and a
prompt fingerprint (`builtin:<hash>`) in both the text summary and JSON
(`meta.semantic`) — and you can pin behavior in CI by pinning the model. See
[ADR-015](docs/adr/ADR-015-sem-stable-intent-not-behavior.md).

> ### ⚠️ Module-level scan is model-sensitive — do not run it on a weak model
>
> Module-level semantic scan (`SEM002`, weak *module* docstrings — opt in with
> `--scan-modes module`; see [ADR-013](docs/adr/ADR-013-module-level-semantic-scan.md))
> is **only reliable on a `gpt-4o`-class model**. On a weak model such as
> `gpt-4o-mini` it produced a **43–71% false-positive rate** on real, well-written
> module docstrings in our validation; on `gpt-4o` the same docstrings came back with
> **0% false positives**.
>
> **Why:** judging a *function* docstring (SEM001) is a tight, local call against the
> signature — `gpt-4o-mini` handles it. Judging a *module* docstring means reasoning
> about whether a one-paragraph description is consistent with the module's whole set
> of public symbols without demanding it enumerate them. Weak models fail that
> distinction: they flag good docstrings for "not listing every symbol." That is a
> false positive, and at 40–70% it will bury the real findings and erode trust in the
> tool.
>
> If you cannot use a `gpt-4o`-class model, **leave module-level scan off**
> (`scan_modes = ["function"]`, the default). Function-level SEM001 remains usable on
> the free `gpt-4o-mini` on-ramp; module-level does not.

### Tool-registry checks (`REG`)

Many projects expose functions to an LLM not through an `@mcp.tool` decorator but
through a **registration record** — a `ToolDefinition`/`ToolSpec` carrying the
name, description, input model, and handler. Add `REG` to `select` and `docpact`
cross-checks those records against the code, **offline, in the default `check`**.

The record is recognized wherever it appears at module level — a `list` of them,
an assignment, a bare expression, or passed straight to a registration call:

```python
class DescribeInput(BaseModel):
    provider_id: str
    region: str

_DESC = """Describe a provider.

Args:
    provider_id: The provider id.
    flags: A field the model does not have.
"""

register_tool(ToolSpec(
    name="describe_provider",
    description=_DESC,                 # a module-level constant is resolved
    input_model=DescribeInput,         # a class defined in this same file
    service_function=describe_provider_tool,
))
```

```toml
[tool.docpact]
select = ["DOC", "REG"]

[tool.docpact.registry]
tool_definition_class = ["ToolSpec"]   # your record class
handler_field = "service_function"     # map your field names (defaults: name/description/input_model/handler)
```

```
$ docpact check tools.py            # no --crossfile, no LSP
tools.py:14:14: REG010 input model 'DescribeInput' field 'region' is not documented in tool 'describe_provider' Args section
tools.py:14:14: REG010 tool 'describe_provider' Args entry 'flags' has no matching field in input model 'DescribeInput'
```

- **REG001** — a JSON-Schema `parameters` key naming a parameter the function lacks.
- **REG010 (same-file)** — the documented `Args:` is out of parity with a
  **same-file** `input_model`'s fields. On by default once `REG` is selected;
  disable with `REG010 = "off"` under `[tool.docpact.rules]`.

It also applies a **Tier-3 floor** to the registered handler — and *only* that
handler, even when the tool name differs from the function name (`name="describe_provider"`,
`service_function=describe_provider_tool`). Unrelated helpers in the same module
keep their tier. See [ADR-011](docs/adr/ADR-011-call-based-tool-registration.md)
and [ADR-012](docs/adr/ADR-012-same-file-reg010-default-pass.md).

### Cross-file mode (`--crossfile`)

The standard `check` is per-file and offline. `--crossfile` extends the `REG`
rules to tool-registry entries that reference **imported** symbols (a model or
handler defined in another module), resolving them via a language server:

- **REG010 (cross-file)** — a tool's documented `Args:` is out of parity with its
  imported `input_model` fields (a model field the docs omit, or a documented arg
  with no matching field). Same rule as the same-file leg above; `--crossfile`
  extends its reach to imported models.
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
pass — fitting for an opt-in CI step, not every keystroke. The LSP resolution is
serial (one session); the per-file analysis still parallelizes (`--jobs`).
Deterministic with a pinned server. **Measure the cost on your own tree before
relying on it — see below.** See [ADR-009](docs/adr/ADR-009-cross-file-via-lsp.md).

### Measuring cross-file cost (`bench --crossfile`)

There is no separate timing flag — the measurement lives in `bench`, the same
command you use to decide `--jobs`. It tells you whether `--crossfile` is cheap
enough for your CI, and *where* its time goes, so you can act on it:

```
$ docpact bench src/ --crossfile
  serial (jobs=1):           327.1 ms   peak 37 MB
  parallel (jobs=16):        122.3 ms   ~16x worker peak 31 MB
  speedup: 2.68x
  cross-file pre-pass:        56.4 ms   (serial, one LSP session; resolved 10 ref(s))
    server spawn + init:       5.4 ms
    queries (20):             42.4 ms total, slowest 32.8 ms
  hint: the slowest single query dominates — that is the server's initial
        workspace index; a persistent/warm server would amortize it across runs.
```

What each line measures:

- **serial / parallel / speedup** — the per-file pass (a normal `check`),
  *unchanged* by `--crossfile`. This is the part `--jobs` parallelizes.
- **cross-file pre-pass** — the wall-time `--crossfile` *adds*: one LSP session
  resolving every imported model/handler, paid once per run. It reports `0.0 ms`
  (and never spawns a server) if your tree has no tool registries.
- **server spawn + init** — launching the language server and the LSP handshake.
- **queries (N) … slowest** — the `textDocument/definition` calls. The slowest
  one usually carries the server's *first* workspace index (built lazily on the
  first query), which is why it dwarfs the rest.

How to use the result — the `hint` line names the lever; the rule of thumb:

| What dominates | What it means | Lever |
|---|---|---|
| `server spawn + init`, or the **slowest query** | the one-time **workspace index** | a persistent/warm server (index once, reuse across runs) |
| the **bulk of `queries`** (total minus the slowest) | per-ref **round-trip latency** | concurrent / pipelined queries in one session |
| nothing — `0.0 ms`, no entries | no cross-file registries | `--crossfile` is free; leave it enabled |

Both levers are designed but **not yet built** (ADR-009) — deliberately gated on
whether real adopter trees turn out index-bound or query-bound, which this is how
you find out. Expect the pre-pass to be **index-bound on large codebases** (the
index grows with project size while per-query work stays cheap) — which points at
a warm server, not more concurrency. Run it once on your repo to know your number.

## What it checks

| Namespace | Rules | What |
|---|---|---|
| `DOC` | DOC001–DOC003, DOC007, DOC012–DOC014, DOC021–DOC022, DOC050, DOC052, DOC099 | Structural completeness: missing docstrings, missing sections, parameter mismatch, default drift, type/prose mismatch, Pydantic field descriptions, required Examples (when configured), stale `[FILL]` markers |
| `TY` | TY001–TY002 | Type/docstring coherence: `-> None` with substantive Returns prose; non-None return with empty Returns |
| `MCP` | MCP001 | MCP-specific conflicts: decorator `description=` duplicates docstring `MCP:` section |
| `FIX` | FIX001–FIX004 | Suppression hygiene: bare suppression comments, missing `-- reason`, stale suppressions, misplaced suppression comments |
| `PARSE` | PARSE001 | Parse-time errors: file contains a Python syntax error and cannot be checked; fires before all other rules |
| `REG` *(opt-in)* | REG001–REG002, REG010 | Tool-registry consistency, same-file and offline: a `ToolDefinition`/`ToolSpec`/dict record (in a list, an assignment, or a registration call like `register_tool(...)`) whose JSON-Schema parameter is absent from the signature (REG001), or whose documented `Args:` is out of parity with a same-file `input_model`'s fields (REG010). Add `REG` to `select`. See below. |
| `REG` *(opt-in, cross-file)* | REG010, REG011 | Cross-file: a tool entry's documented `Args:` out of parity with its **imported** `input_model` fields (REG010, imported-model leg), or a declared parameter the **imported** `handler` does not accept (REG011). Resolved via an LSP server; run only under `docpact check --crossfile`. See below. |
| `SEM` *(opt-in, advisory)* | SEM001, SEM002 | Meaning, not structure: LLM-judged. SEM001 — a *function* docstring that's cargo-cult, hides a precondition/constraint, or has an empty Returns. SEM002 — a *module* docstring out of scope with its symbols or pure boilerplate (opt in with `--scan-modes module`; **gpt-4o-class model only**, see warning above). Run via `docpact semantic` — never part of `check`; non-deterministic and advisory. |

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

If the custom registry is a same-file record — a `list[ToolDefinition]`, a list of `{"name", "description", "parameters"}` dicts, or a `register_tool(ToolSpec(...))` call — enabling the `REG` namespace is more precise than a glob: only the function each entry registers is held to the Tier 3 floor, not every function in the file. The floor follows the entry's `handler` when the tool name and function name differ. See the `[tool.docpact.registry]` config below.

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
tool_definition_class = ["ToolDefinition"]   # record class name(s); flat dict literals also recognized
# Recognized in a list, an assignment, a bare expression, or a registration call
# such as register_tool(ToolSpec(...)). Map your field names if they differ:
# name_field = "name"
# description_field = "description"          # a module-level string constant is resolved
# input_model_field = "input_model"         # same-file class → offline REG010
# handler_field = "handler"                  # the function the Tier 3 floor lands on
# assign_tier = true                         # registry membership → Tier 3 floor (default)
# no_tier_floor = ["src/legacy/**"]          # files where the floor is not applied

# Opt-in: advisory LLM semantic check (`docpact semantic`). Pluggable backend.
[tool.docpact.semantic]
backend = "openai-compat"                    # OpenAI-compatible: GitHub Models, OpenAI, Gemini, Ollama, vLLM…
model = "openai/gpt-4o-mini"
api_base = "https://models.github.ai/inference"   # e.g. GitHub Models (free to try)
api_key_env = "GITHUB_TOKEN"                 # name of the env var holding the key — never the key
# Gemini works via its OpenAI-compatible endpoint — no extra adapter:
#   api_base = "https://generativelanguage.googleapis.com/v1beta/openai"
#   model = "gemini-2.5-pro"                 # gpt-4o-class; flash-tier is cheaper but weaker for SEM002
#   api_key_env = "GEMINI_API_KEY"
# min_tier = 3                               # scope to agent-facing tools (default 3)
# finding_threshold = "weak"                 # "weak" surfaces weak+empty; "empty" only the vacuous
# scan_modes = ["function"]                  # add "module" for SEM002 — gpt-4o-class model ONLY (see ⚠️ above)
# max_retries = 2                            # retries on transient 429/5xx with backoff (0 disables)

# Opt-in: cross-file analysis (imported models/handlers) via an LSP server.
# Used only by `check --crossfile`; the same-file REG010 leg needs none of this.
[tool.docpact.lsp]
server = ["ty", "server"]                    # any LSP-conformant server: ["pyright-langserver", "--stdio"], …
# timeout = 15.0                             # seconds per request / definition readiness budget
# log = "lsp.log"                            # append the server's stderr here (default: discard);
                                             # override per-run with `check --lsp-log PATH`
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
    rev: v0.1.0a12
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

Self-hosting: `docpact` validates its own source on every commit. 1069 tests, 94% coverage.

Active rules: DOC001–DOC003, DOC007, DOC012–DOC014, DOC021–DOC022, DOC050, DOC052, DOC099, MCP001, FIX001–FIX004, TY001–TY002, PARSE001, REG001–REG002, SEM001 (advisory).

## Documentation

| Document | Purpose |
|---|---|
| [Specification](docs/spec/docpact-spec.md) | Full design specification. Source of truth for what docpact is and why. |
| [Rule docs](docs/rules/) | One page per rule: what it checks, examples, configuration. |
| [ADR index](docs/adr/README.md) | Architecture decision records. Why each significant choice was made. |
| [Progress](docs/PROGRESS.md) | Spec-cycle milestone log and per-phase status. |

## License

MIT. See [LICENSE](LICENSE).

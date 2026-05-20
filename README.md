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
docpact generate src/                 # insert stub docstrings for undocumented functions
docpact list-rules                    # list all rules with severity and fixability
```

## What it checks

| Namespace | Rules | What |
|---|---|---|
| `DOC` | DOC001–DOC003, DOC007, DOC012–DOC014, DOC021–DOC022, DOC050, DOC099 | Structural completeness: missing docstrings, missing sections, parameter mismatch, default drift, type/prose mismatch, Pydantic field descriptions, stale `[FILL]` markers |
| `TY` | TY001–TY002 | Type/docstring coherence: `-> None` with substantive Returns prose; non-None return with empty Returns |
| `MCP` | MCP001 | MCP-specific conflicts: decorator `description=` duplicates docstring `MCP:` section |
| `FIX` | FIX001–FIX004 | Suppression hygiene: bare suppression comments, missing `-- reason`, stale suppressions, misplaced suppression comments |
| `PARSE` | PARSE001 | Parse-time errors: file contains a Python syntax error and cannot be checked; fires before all other rules |

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

[tool.docpact.per-file-ignores]
"src/generated/*" = ["DOC"]
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
    rev: v0.1.0a2
    hooks:
      - id: docpact
```

## Boundaries

`docpact` checks structure, not meaning. A docstring that passes every check is not necessarily a good docstring. It is a *consistent* one: the Args match the signature, the required sections are present, the types don't contradict the prose. Content quality — whether the description is actually useful — is the author's responsibility.

It does not replace ruff or ty. It does not import the code it analyzes. It does not perform LLM-based semantic analysis (designed in the spec, explicitly deferred).

## Status

Self-hosting: `docpact` validates its own source on every commit. 774 tests, 94% coverage.

Active rules: DOC001–DOC003, DOC007, DOC012–DOC014, DOC021–DOC022, DOC050, DOC099, MCP001, FIX001–FIX004, TY001–TY002, PARSE001.

## Documentation

| Document | Purpose |
|---|---|
| [Specification](docs/spec/docpact-spec.md) | Full design specification. Source of truth for what docpact is and why. |
| [Rule docs](docs/rules/) | One page per rule: what it checks, examples, configuration. |
| [ADR index](docs/adr/README.md) | Architecture decision records. Why each significant choice was made. |
| [Progress](docs/PROGRESS.md) | Milestone log and v0.2 scope. |

## License

MIT. See [LICENSE](LICENSE).

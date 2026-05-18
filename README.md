# docpact

A linter and validator for Python docstrings — built for the audiences that treat them as machine-readable contracts.

---

Python functions exposed as MCP tools, FastAPI routes, or called by coding agents publish their contracts through docstrings. Those docstrings are now read by machines making consequential decisions: which tool to invoke, which arguments to pass, whether a proposed change is safe. A stale or inconsistent docstring silently misdirects them.

docpact validates that required sections are present for the function's exposure tier, that documented parameters match the signature, and that the type annotation and the prose don't contradict each other. It fails fast on drift and provides safe automated fixes for the unambiguous cases.

```
$ docpact check src/
src/notify.py:12:0: DOC012 Tier 3 function missing required section: Constraints
src/notify.py:12:0: DOC012 Tier 3 function missing required section: Stability
src/payments.py:8:0: DOC007 Documented parameter not in signature: amout (did you mean: amount?)
src/users.py:31:0: TY001 Return annotation is 'None' but Returns section documents a value
Found 4 errors.
```

## Install

```bash
pip install docpact
# or
uv add docpact
```

## Usage

```bash
docpact check src/                    # check all .py files under src/
docpact check src/ --fix              # apply safe fixes in-place
docpact check src/ --diff             # preview fixes as a unified diff
docpact check src/ --format sarif     # SARIF 2.1.0 for GitHub Code Scanning
docpact check src/ --format json      # machine-readable JSON
docpact generate src/                 # insert stub docstrings for undocumented functions
docpact list-rules                    # list all rules with severity and fixability
```

## What it checks

| Namespace | Rules | What |
|---|---|---|
| `DOC` | DOC001–DOC003, DOC007, DOC012–DOC014, DOC050–DOC051, DOC099 | Structural completeness: missing docstrings, missing sections, parameter mismatch, Pydantic field descriptions, stale `[FILL]` markers |
| `TY` | TY001–TY002 | Type/docstring coherence: annotation vs. prose contradictions |
| `MCP` | MCP001 | MCP-specific conflicts: decorator `description=` vs. docstring `MCP:` section |
| `FIX` | FIX001–FIX002 | Suppression hygiene: bare suppression comments, missing `-- reason` |

Full rule documentation: [`docs/rules/`](docs/rules/).

## Tier model

docpact assigns each function a *tier* based on who consumes it and enforces the appropriate schema:

| Tier | Who | Required sections |
|---|---|---|
| 1 | Internal | Summary |
| 2 | Package-public API | Summary, Args (when params present), Returns (when non-None) |
| 3 | MCP-exposed tools | Tier 2 + Raises, Constraints, Stability, MCP |
| 4 | FastAPI routes via FastMCP | Same as Tier 3 |

Tier assignment is automatic from decorators and file structure. Overrides are available in config.

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

Inline suppression (on the `def` line):

```python
def build_internal_graph(  # nodo: DOC012 -- internal; tier override not yet wired
    nodes: list[str],
) -> Graph: ...
```

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
  - repo: https://github.com/your-org/docpact
    rev: v0.1.0
    hooks:
      - id: docpact
```

## What docpact does NOT do

- Does not replace ruff, ty, or any type checker — it validates the docstring layer specifically.
- Does not verify behavioral correctness — it checks structural consistency. See spec §1.4.
- Does not import the code under analysis — all checks are purely static.
- Does not perform LLM-based semantic analysis in v0.1 — that mode is designed in the spec but explicitly deferred.

## Status

v0.1 complete. Self-hosting: docpact checks its own source on every CI run.

Active rules: DOC001–DOC003, DOC007, DOC012–DOC014, DOC050–DOC051, DOC099, MCP001, FIX001–FIX002, TY001–TY002. 558 tests, 96% coverage.

## Documentation

| Document | Purpose |
|---|---|
| [Specification](docs/spec/docpact-spec.md) | Full design specification. Source of truth for what docpact is and why. |
| [Rule docs](docs/rules/) | One page per rule: what it checks, examples, configuration. |
| [ADR index](docs/adr/README.md) | Architecture decision records. Why each significant choice was made. |
| [Progress](docs/PROGRESS.md) | Milestone log and v0.2 scope. |

## License

MIT. See [LICENSE](LICENSE).

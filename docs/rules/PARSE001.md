# PARSE001 — File contains a Python syntax error and cannot be parsed

**Namespace:** `PARSE`  
**Severity:** 🔴 error  
**Fix:** No automatic fix

---

## Description

Fires when a Python file contains invalid syntax and cannot be parsed. When PARSE001 fires, `docpact` skips all other checks for that file — structural analysis requires a valid AST.

The diagnostic is placed at the line and column reported by the Python interpreter for the syntax error. The message is the interpreter's error text (e.g. `invalid syntax`, `unexpected EOF`).

PARSE001 is in the `PARSE` namespace, which is selected by default alongside `DOC` and `MCP`. It can be disabled project-wide or suppressed per-file using `per-file-ignores` (useful for generated or vendored files that are intentionally not valid Python).

## Examples

### Triggering

```python
def bad(:
    pass
```

PARSE001 fires: the colon before the parameter list makes this invalid syntax. No other checks run for this file.

### Passing

```python
def good() -> None:
    """Do nothing."""
    pass
```

Valid Python — PARSE001 does not fire and all other enabled rules are checked normally.

## Configuration

Disable globally (not recommended — syntax errors are always worth surfacing):

```toml
[tool.docpact]
ignore = ["PARSE001"]
```

Suppress for generated or vendored files:

```toml
[tool.docpact.per-file-ignores]
"src/generated/*" = ["PARSE001"]
```

Suppress inline (on the first line of the file; `parse_suppressions` is text-based and handles broken files):

```python
# nodo: PARSE001 -- generated file, intentionally invalid during build
def bad(:
    ...
```

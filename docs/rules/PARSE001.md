# PARSE001 — File contains a Python syntax error and cannot be parsed

**Namespace:** `PARSE`  
**Severity:** 🔴 error  
**Fix:** No automatic fix

---

## Description

<!-- TODO: expand the description for PARSE001 -->

## Examples

### Triggering

```python
# PARSE001 fires here — add a concrete example
```

### Passing

```python
# PARSE001 does not fire here — add a concrete example
```

## Configuration

This rule can be disabled with:

```toml
[tool.docpact]
ignore = ["PARSE001"]
```

Or suppressed inline:

```python
def my_function(  # nodo: PARSE001 -- reason
    ...
```

# Plan: PARSE001 — Python Syntax Error Rule

**Status:** Ready to implement  
**Scope:** New registered rule that fires when a file cannot be parsed; flows through all output formatters (text, JSON, SARIF).  
**Prerequisite:** None. Implement in a fresh session.

---

## Problem

`docpact check bad.py` crashes with an unhandled `SyntaxError` traceback when the input file contains invalid Python. The `extract_functions()` call in `_run_checks` (`cli.py:217`) propagates the exception uncaught. JSON and SARIF users get no structured output.

---

## Architecture overview

- Rules live in `src/docpact/rules/<namespace>/<code>_<slug>.py`, decorated with `@register(RuleMetadata(...))`.
- `RuleResult` (`model/diagnostic.py`) flows through all formatters unchanged — no formatter changes needed.
- File-level rules (DOC002, DOC003, DOC050, FIX001–FIX003) are wired directly in `_run_checks` and skipped in the function-level loop via `_FILE_LEVEL_CODES`. PARSE001 follows the same pattern.
- `extract_functions` (`parser/source.py:109`) declares `Raises: SyntaxError` and does not catch it.

---

## Files to create

### `src/docpact/rules/parse/__init__.py`

Pure module docstring, no code — matches `doc/__init__.py`, `fix/__init__.py`, etc.:

```python
"""PARSE namespace — parse-time error rules.

Rules in this namespace fire when a Python file cannot be parsed at all.
They run before any function- or file-level structural rules are evaluated.
"""
```

### `src/docpact/rules/parse/parse001_syntax_error.py`

**`RuleMetadata` fields:**
- `code = "PARSE001"`
- `namespace = "PARSE"`
- `summary = "File contains a Python syntax error and cannot be parsed"`
- `default_severity = Severity.ERROR` — hard error, blocks all other checks
- `fixable = False`, `unsafe_fixable = False`

**Stub `check` function** (no-op, keeps PARSE001 visible in `list-rules`):
```python
@register(RuleMetadata(...))
def check(func: FunctionInfo, doc: ParsedDocstring | None, cfg: RuleConfig) -> list[RuleResult]:
    """Stub — PARSE001 is wired as a file-level rule in _run_checks."""
    return []
```

**Real implementation** `check_syntax_error`:
```python
def check_syntax_error(
    exc: SyntaxError,
    file_path: Path,
    config: RuleConfig,
) -> RuleResult:
```

Extracting position from `SyntaxError`:
- Line: `exc.lineno if exc.lineno is not None else 1`
- Column: `(exc.offset - 1) if exc.offset is not None and exc.offset > 0 else 0`
  (converts 1-based `offset` to 0-based column; guards `offset=0` edge case)
- Message: use `exc.msg` (not `str(exc)`) to avoid the `(<string>, line N)` suffix

---

## Files to modify

### `src/docpact/rules/__init__.py`

Inside `load_builtin_rules()`, add (alphabetically between mcp and ty):
```python
import docpact.rules.parse.parse001_syntax_error
```

### `src/docpact/cli.py`

**Import** (alongside other file-level check function imports, lines ~51–57):
```python
from docpact.rules.parse.parse001_syntax_error import check_syntax_error as check_parse_syntax_error
```

**`_FILE_LEVEL_CODES`** (line 144): add `"PARSE001"`:
```python
_FILE_LEVEL_CODES: frozenset[str] = frozenset(
    {"FIX001", "FIX002", "FIX003", "DOC002", "DOC003", "DOC050", "PARSE001"}
)
```

**`_run_checks` body** — wrap `extract_functions` (currently line 217) in try/except:
```python
all_names = parse_all_names(source_text)
source_lines = source_text.splitlines()

try:
    functions = extract_functions(file_path)
except SyntaxError as exc:
    if (
        "PARSE001" in rules
        and rule_is_enabled("PARSE001", "PARSE", config.select, config.ignore)
        and not rule_is_file_ignored("PARSE001", "PARSE", extra_ignores)
    ):
        meta, _ = rules["PARSE001"]
        severity = config.rule_severities.get("PARSE001", meta.default_severity)
        if severity != Severity.OFF:
            cfg = RuleConfig(severity=severity, options={})
            file_results.append(check_parse_syntax_error(exc, file_path, cfg))
    results.extend(file_results)
    continue  # skip function-level loop and FIX003 post-pass for this file
```

The `continue` skips the `for func in functions:` loop and the FIX003 post-pass. `results.extend(file_results)` before `continue` is required so PARSE001 enters the global accumulator.

Note: `parse_suppressions` (line 164, before this block) is text-based and handles invalid Python fine. File-level pre-pass rules (DOC002, DOC003, DOC050, FIX001, FIX002) all have their own `except SyntaxError: return []` guards and run correctly even on broken files.

### `src/docpact/config.py`

The `Config` dataclass default select (line ~51) and `_parse_section` local default (line ~94) both have `("DOC", "MCP")`. Update both to include `"PARSE"`:
```python
select: tuple[str, ...] = ("DOC", "MCP", "PARSE")
```

### `pyproject.toml`

Add `"PARSE"` to `[tool.docpact]` select so the self-check exercises the new namespace:
```toml
select = ["DOC", "MCP", "FIX", "TY", "PARSE"]
```

---

## File to create

### `tests/test_rules/test_parse001.py`

**Unit tests for `check_syntax_error`:**
1. `test_syntax_error_fires` — real `SyntaxError` from `ast.parse("def (:\n")` → `code == "PARSE001"`, `severity == ERROR`.
2. `test_syntax_error_line_reported` — `result.location.line == exc.lineno`.
3. `test_syntax_error_column_reported` — `result.location.column == exc.offset - 1`.
4. `test_syntax_error_message_contains_msg` — `exc.msg in result.message`.
5. `test_syntax_error_none_lineno_falls_back_to_line_1` — `SyntaxError(lineno=None, offset=None)` → location `(1, 0)`.
6. `test_severity_from_config` — `RuleConfig(severity=WARNING)` → result severity is `WARNING`.
7. `test_result_is_not_fixable` — `result.fix is None` and `result.unsafe_fix is None`.
8. `test_stub_check_function_returns_empty` — stub `check(func, None, cfg)` returns `[]`.

**CLI integration tests:**
9. `test_syntax_error_file_exits_one_text_format` — bad file, `--select PARSE`, exit code 1, `"PARSE001"` in output.
10. `test_syntax_error_file_json_format` — bad file, `--format json`, parse JSON, `code == "PARSE001"`.
11. `test_syntax_error_file_sarif_format` — bad file, `--format sarif`, `ruleId == "PARSE001"` in results.
12. `test_parse001_not_selected_by_doc_select` — `select = ["DOC"]` → PARSE001 does not appear.
13. `test_parse001_selected_by_parse_prefix` — `--select PARSE` fires PARSE001.
14. `test_parse001_severity_off_suppresses` — `PARSE001 = "off"` in rule severities → no output.
15. `test_parse001_inline_suppression` — `# nodo: PARSE001` on the error line → no output.

---

## Spec update

`docs/spec/docpact-spec.md` needs a new section or entry for the PARSE namespace and PARSE001. At minimum, add it to the rule registry table (§18 or wherever existing rules are enumerated) and note that PARSE rules fire before structural analysis. Confirm with Ray before editing the spec — per CLAUDE.md, spec changes are stop-and-ask territory.

## Docs

Run `make docs` after all code changes. It auto-generates `docs/rules/PARSE001.md`. Commit the generated file — `make verify` (docs-check step) will fail if it's missing.

The new `parse001_syntax_error.py` will be scanned by dogfood. `check_syntax_error` needs a full docstring (Args, Returns, Raises, Stability) to pass DOC012 at Tier 2. The stub `check` function is covered by the existing per-file-ignore `"src/docpact/rules/*/*.py" = ["DOC012"]` and only needs a summary line.

---

## Edge cases

- `SyntaxError.offset = 0`: guard with `offset > 0` before subtracting 1; fall back to column 0.
- `OSError` from `extract_functions`: separate bug, out of scope.
- FIX003 post-pass: skipped by `continue` — correct, since there are no function-level results to diff.
- Suppression matching: `parse_suppressions` is text-based and works on invalid Python; `# nodo: PARSE001` on the error line suppresses normally through `apply_suppressions`.

---

## Execution order

1. Create `src/docpact/rules/parse/__init__.py`
2. Create `src/docpact/rules/parse/parse001_syntax_error.py`
3. Edit `src/docpact/rules/__init__.py` — add import in `load_builtin_rules()`
4. Edit `src/docpact/cli.py` — import, `_FILE_LEVEL_CODES`, try/except block
5. Edit `src/docpact/config.py` — add `"PARSE"` to default select (two places)
6. Edit `pyproject.toml` — add `"PARSE"` to self-check select
7. Create `tests/test_rules/test_parse001.py`
8. Run `make docs` → commits `docs/rules/PARSE001.md`
9. Run `make verify`

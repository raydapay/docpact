# Plan: AST-Aware Suppression Scanner via `tokenize`

**Status:** Ready to implement  
**Scope:** Fix `parse_suppressions` to skip suppression patterns inside string literals. Remove the `per-file-ignores` FIX003 workaround from `pyproject.toml`.  
**Prerequisite:** None. Can be implemented in a clean session before or after PARSE001.

---

## Problem

`parse_suppressions` in `src/docpact/suppress.py` does a line-by-line text scan. It cannot distinguish between a real comment (`# nodo: DOC001 -- reason`) and the same pattern appearing inside a string literal (e.g., in a module docstring used as documentation). This causes FIX003 false positives on 7 files that contain suppression syntax examples in their docstrings.

Current workaround: `per-file-ignores` entries in `pyproject.toml` that suppress FIX003 for those files, with a comment explaining the limitation. This plan eliminates the root cause and removes the workaround.

---

## Solution

Replace the text-scan loop in `parse_suppressions` with `tokenize.generate_tokens`. The `tokenize` module (stdlib, no new dependencies) emits `COMMENT` tokens only for real Python comments — never for text inside string literals, including triple-quoted docstrings. This is the correct semantic level.

---

## Files to modify

### `src/docpact/suppress.py`

**Add imports:**
```python
import io
import tokenize
```
(`re` stays — still used by `_build_re`.)

**Replace the body of `parse_suppressions`** (keep signature identical):

Current loop (text-based):
```python
for lineno, line in enumerate(source.splitlines(), start=1):
    m = pattern.search(line)
    if m is None:
        continue
    ...
```

New loop (tokenize-based):
```python
result: dict[int, frozenset[str]] = {}
try:
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        m = pattern.search(tok.string)
        if m is None:
            continue
        lineno = tok.start[0]   # 1-based, matches existing convention
        codes_str = m.group(1)
        if codes_str is None:
            result[lineno] = frozenset()           # bare suppression
        else:
            result[lineno] = frozenset(c.strip() for c in codes_str.split(","))
except tokenize.TokenError:
    # Source has an unclosed string or other tokenize-level error.
    # Return partial results — caller handles broken files at a higher level.
    pass
return result
```

Key points:
- `tok.string` is the full comment text from `#` to end of content (no trailing newline). The existing regex already anchors to `#`, so it matches correctly.
- `tok.start[0]` is 1-based line number — identical convention to the old `enumerate(..., start=1)`.
- `tokenize.TokenError` is raised on incomplete source (e.g., unclosed `"""`). Partial results are returned rather than crashing, because the caller (`_run_checks`) handles parse failures separately.
- `_build_re`, `is_suppressed`, and `apply_suppressions` are **unchanged**.
- All callers use the same `(source: str, *, markers: tuple[str, ...]) -> dict[int, frozenset[str]]` signature — **no caller changes needed**.

### `tests/test_suppress.py`

Add a section at the end (e.g., `# --- tokenize-based scanner: string literal isolation ---`) with these new tests:

**1. Triple-quoted docstring: NOT picked up**
```python
def test_suppression_in_triple_quoted_docstring_not_picked_up() -> None:
    source = (
        'def foo():\n'
        '    """Example:\n'
        '        # nodo: DOC001 -- this is in a docstring\n'
        '    """\n'
        '    pass\n'
    )
    assert parse_suppressions(source) == {}
```

**2. Real comment: IS picked up (regression guard)**
```python
def test_suppression_in_real_comment_is_picked_up() -> None:
    source = 'def foo(): pass  # nodo: DOC007 -- reason\n'
    assert parse_suppressions(source) == {1: frozenset({"DOC007"})}
```

**3. Mixed file: docstring line ignored, real comment captured**
```python
def test_mixed_file_docstring_ignored_real_comment_captured() -> None:
    source = (
        '"""Module with # nodo: DOC001 -- in module docstring."""\n'
        '\n'
        'def foo(): pass  # nodo: DOC007 -- real\n'
    )
    result = parse_suppressions(source)
    assert result == {3: frozenset({"DOC007"})}
    assert 1 not in result
```

**4. Single-quoted string: NOT picked up**
```python
def test_suppression_in_single_quoted_string_not_picked_up() -> None:
    source = 'x = "# nodo: DOC001 -- in string"\ny = 1\n'
    assert parse_suppressions(source) == {}
```

**5. f-string: NOT picked up**
```python
def test_suppression_in_fstring_not_picked_up() -> None:
    source = 'x = f"message: {v}  # nodo: DOC001"\ny = 1\n'
    assert parse_suppressions(source) == {}
```

**6. `tokenize.TokenError`: returns empty dict, does not raise**
```python
def test_tokenize_error_returns_empty_dict() -> None:
    source = 'x = 1\ny = """unclosed\n'
    result = parse_suppressions(source)
    assert isinstance(result, dict)
```

**7. Partial results before `TokenError`**
```python
def test_tokenize_error_partial_results_returned() -> None:
    # Line 1 has a valid comment; line 2 opens an unclosed string.
    source = 'x = 1  # nodo: DOC001 -- reason\ny = """unclosed\n'
    result = parse_suppressions(source)
    # COMMENT token for line 1 is emitted before TokenError on line 2.
    assert result == {1: frozenset({"DOC001"})}
```

### `pyproject.toml`

Remove the 7 FIX003 `per-file-ignores` entries added as workaround (the entire block from "These files contain inline examples..." through the last `"src/docpact/rules/doc/doc003_class_docstring.py" = ["FIX003"]` line).

Keep the DOC012 entry — it is unrelated:
```toml
[tool.docpact.per-file-ignores]
"src/docpact/rules/*/*.py" = ["DOC012"]
```

---

## Correctness notes

**Triple-quoted strings across multiple lines:** `tokenize` produces a single `STRING` token for the entire triple-quoted string, even when it spans many lines. No line within that span produces a `COMMENT` token. This is the exact guarantee needed.

**`#nodo:` with no space:** `_build_re` uses `\s*` between `#` and the marker word, so this still matches correctly when applied to `tok.string`.

**`tok.string` format:** Always starts with `#` and contains the comment content without a trailing newline. The existing regex works unchanged.

**`tokenize.COMMENT` constant:** Named constant (integer 61 on CPython 3.12+). Use the named constant, not the literal.

---

## Execution order

1. Edit `src/docpact/suppress.py` — add `import io, tokenize`; replace the text-scan loop.
2. Add 7 new tests to `tests/test_suppress.py`.
3. Edit `pyproject.toml` — remove the 7 FIX003 per-file-ignores entries.
4. Run `make verify`.

Steps 1–3 can be done in any order; all three must be complete before step 4 can pass (dogfood will fail if the workaround is removed before the scanner is fixed).

---

## Spec update

`docs/spec/docpact-spec.md` §15.2 (suppression parsing) may describe the current text-scan behavior. After implementing the fix, verify whether that section's language implies a text scan or is agnostic. If it says anything about comments vs. string literals, update it. Confirm with Ray — spec edits are stop-and-ask per CLAUDE.md.

## Verification

`make verify` passes when:
- All existing suppression tests still pass (same observable behaviour for real comments).
- New tests 1–7 pass.
- Dogfood (`make dogfood`) runs clean with no FIX003 warnings and no per-file-ignores workaround.
- Coverage stays ≥ 85% (the `except tokenize.TokenError` branch is covered by tests 6 and 7).

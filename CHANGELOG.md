# Changelog

Generated from conventional commits. Only `feat:` and `fix:` entries appear.
## [0.1.0a2] — 2026-05-20

### Fixed
- Explicit utf-8 encoding on all read_text/write_text calls
- **ci:** Non-mutating verify-ci gate for CI and release pipeline
- Lower `requires-python` from `>=3.12` to `>=3.11`, restoring Python 3.11 compatibility


## [0.1.0a1] — 2026-05-19

### Added
- **suppress:** Introduce `# nodo: CODE -- reason` inline suppression syntax with configurable markers
- **suppress:** `--add-suppression` flag for one-step baselining of existing violations; `--suppression-reason` to customise the reason text
- **rules:** DOC001 (missing docstring), DOC002 (missing module docstring), DOC003 (missing class docstring)
- **rules:** DOC007 (Args/signature mismatch), DOC012 (required section missing for tier)
- **rules:** DOC013 (non-canonical empty section), DOC014 (parameter name likely typo)
- **rules:** DOC021 ("Defaults to X" prose drift), DOC022 (typed prose annotation mismatch)
- **rules:** DOC050 (Pydantic field missing `Field(description=...)`)
- **rules:** DOC099 (stale `[FILL]` placeholder)
- **rules:** MCP001 (decorator `description=` duplicates docstring `MCP:` section)
- **rules:** FIX001 (bare suppression), FIX002 (suppression without `-- reason`), FIX003 (stale suppression)
- **rules:** TY001 (Returns section with `-> None`), TY002 (no Returns section with non-None return)
- **rules:** PARSE001 (Python syntax error prevents parsing)
- **parser:** NumPy docstring format support (`format = "numpy"` in config)
- **output:** SARIF 2.1.0 (`--format sarif`), GitHub Actions annotations (`--format github`), JSON (`--format json`)
- **output:** Color diagnostics with `--color auto|always|never`; `--output-file` to write output to a file
- **cli:** `--changed-only <ref>` restricts checks to files changed relative to a git ref
- **cli:** `--config PATH` for explicit config file, bypassing CWD discovery
- **tiers:** `__all__` awareness in tier assignment; `[tool.docpact.per-file-tier]` config key
- **tiers:** Inline tier pragma `# docpact: tier=N` on `def` lines (opt-in via `allow_pragma = true`)
- **api:** `docpact.testing` programmatic assertions API
- **commands:** `docpact generate` (stub docstrings), `docpact show-schema`, `docpact list-rules`


### Fixed
- **DOC002:** Exclude `__init__.py` files by default
- **DOC021:** Strip rST backticks, unwrap `F(literal)` defaults, literals only
- **suppress:** Use tokenize to skip string literals in suppression scan




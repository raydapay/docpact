"""Source and docstring parsing.

Two distinct concerns:

- `source` extracts FunctionInfo from Python source files using the
  standard-library ast module. No imports, no execution.
- `docstring` parses the docstring text into ParsedDocstring using
  griffe. Format-specific; v0.1 ships the Google parser.

The DocstringParser interface (spec §7.2) is realized here. Adding NumPy
or Sphinx support in later versions involves only this package; the rule
engine is unaffected.
"""

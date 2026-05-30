"""Cross-file resolution layer — a provider-agnostic LSP client (ADR-009).

Unlike `check`, which is per-file and offline, the LSP layer resolves an
imported symbol to its *defining file* by driving a language server over the
Language Server Protocol. docpact then does its own AST extraction on that
file; the server does only the import resolution it is purpose-built for. This
keeps docpact's no-import/no-execution guarantee (servers resolve statically)
while delegating the one thing a per-file linter cannot do itself.

The server is configured (`[tool.docpact.lsp]`, command + args), defaulting to
ty. Any LSP-conformant server — pyright, pylsp, jedi — is a drop-in swap:
docpact depends on the *protocol*, not on any one vendor. This is the same
pluggability the SEM backend chose (ADR-008).

It is strictly opt-in. The default `check` never touches this layer, so its
determinism, speed, and offline guarantees are unaffected. When no server is
available the client raises `LSPError` rather than crashing, so callers degrade
gracefully.
"""

from docpact.lsp.client import LSPClient, LSPError, LspLocation

__all__ = ["LSPClient", "LSPError", "LspLocation"]

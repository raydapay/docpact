"""Cross-file analysis pass (ADR-009) — opt-in, LSP-backed.

Resolves each tool-registration entry's imported ``input_model`` to its
defining file via the LSP client, AST-extracts the model's fields, and compares
them to the entry's documented ``Args:`` (REG010). It is the orchestration that
ties together the LSP client (``docpact.lsp``), registry extraction
(``docpact.parser.registry``), Pydantic field reading
(``docpact.parser.pydantic_model``), and the REG010 comparison.

Invoked only by ``docpact check --crossfile``. The default per-file ``check``
never imports or runs this, so it stays offline and deterministic. A missing or
failing server surfaces as ``LSPError`` for the caller to report — the pass
never crashes the run.
"""

from docpact.crossfile.resolver import CrossfileResult, resolve_crossfile

__all__ = ["CrossfileResult", "resolve_crossfile"]

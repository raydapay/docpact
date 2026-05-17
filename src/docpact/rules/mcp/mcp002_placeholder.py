"""MCP002 — not implemented in v0.1.

The structural case this rule was intended to cover ("Tier 3 function has
neither a docstring MCP: section nor a decorator description=") is already
handled by DOC012 (required section missing for tier).

The quality/completeness variant ("the description present is too short or
unhelpful") requires semantic understanding and belongs in the SEM namespace
when semantic mode ships (spec §5.3).

See CLAUDE.md and the planning session notes for the full resolution.
"""

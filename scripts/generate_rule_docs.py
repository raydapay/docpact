"""Generate one Markdown page per rule code in docs/rules/.

Run from the project root:

    uv run python scripts/generate_rule_docs.py

Reads rule metadata from the live registry (requires all rule modules to be
importable). Writes or overwrites docs/rules/<code>.md for every registered
rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the src layout is importable when run from the project root.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Rule modules must be imported before the registry is populated.
import docpact.rules.doc.doc001_missing_docstring  # noqa: F401, E402
import docpact.rules.doc.doc002_module_docstring  # noqa: F401, E402
import docpact.rules.doc.doc007_param_mismatch  # noqa: F401, E402
import docpact.rules.doc.doc012_missing_section  # noqa: F401, E402
import docpact.rules.doc.doc013_noncanonical_empty  # noqa: F401, E402
import docpact.rules.doc.doc014_suspicious_param  # noqa: F401, E402
import docpact.rules.doc.doc050_pydantic_field  # noqa: F401, E402
import docpact.rules.doc.doc051_annotated_constraint  # noqa: F401, E402
import docpact.rules.doc.doc098_doctest_exception  # noqa: F401, E402
import docpact.rules.doc.doc099_fill_marker  # noqa: F401, E402
import docpact.rules.fix.fix001_bare_noqa  # noqa: F401, E402
import docpact.rules.fix.fix002_no_reason  # noqa: F401, E402
import docpact.rules.mcp.mcp001_decorator_docstring_conflict  # noqa: F401, E402
from docpact.rules._registry import all_rules  # noqa: E402

FIXABILITY_NOTES = {
    (True, False): "Safe fix available (`--fix`)",
    (True, True): "Safe fix (`--fix`) and unsafe fix (`--unsafe-fixes`) available",
    (False, True): "Unsafe fix available (`--unsafe-fixes`)",
    (False, False): "No automatic fix",
}


def _severity_badge(severity: str) -> str:
    return {"error": "🔴 error", "warning": "🟡 warning", "off": "⚪ off"}.get(severity, severity)


def _page(code: str, meta: object) -> str:
    from docpact.model.diagnostic import Severity

    sev = meta.default_severity.value  # type: ignore[union-attr]
    fixability = FIXABILITY_NOTES[(meta.fixable, meta.unsafe_fixable)]  # type: ignore[union-attr]

    lines = [
        f"# {code} — {meta.summary}",  # type: ignore[union-attr]
        "",
        f"**Namespace:** `{meta.namespace}`  ",  # type: ignore[union-attr]
        f"**Severity:** {_severity_badge(sev)}  ",
        f"**Fix:** {fixability}",
        "",
        "---",
        "",
        "## Description",
        "",
        f"<!-- TODO: expand the description for {code} -->",
        "",
        "## Examples",
        "",
        "### Triggering",
        "",
        "```python",
        f"# {code} fires here — add a concrete example",
        "```",
        "",
        "### Passing",
        "",
        "```python",
        f"# {code} does not fire here — add a concrete example",
        "```",
        "",
        "## Configuration",
        "",
        "This rule can be disabled with:",
        "",
        "```toml",
        "[tool.docpact]",
        f'ignore = ["{code}"]',
        "```",
        "",
        "Or suppressed inline:",
        "",
        "```python",
        f"def my_function(  # nodo: {code} -- reason",
        "    ...",
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    """Generate docs/rules/<code>.md for every registered rule."""
    out_dir = Path(__file__).parent.parent / "docs" / "rules"
    out_dir.mkdir(parents=True, exist_ok=True)

    rules = all_rules()
    for code, (meta, _) in sorted(rules.items()):
        page_path = out_dir / f"{code}.md"
        page_path.write_text(_page(code, meta))
        print(f"  wrote {page_path.relative_to(Path(__file__).parent.parent)}")

    print(f"\nGenerated {len(rules)} rule pages in {out_dir.relative_to(Path(__file__).parent.parent)}/")


if __name__ == "__main__":
    main()

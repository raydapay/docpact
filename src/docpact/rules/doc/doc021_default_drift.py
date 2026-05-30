"""DOC021 — "Defaults to X" in Args prose does not match the signature default.

Fires when an Args entry contains a ``Defaults to <value>`` phrase whose
value does not match the parameter's actual default in the function
signature.

Example of a drift that triggers DOC021:
    def fetch(count: int = 5) -> list:
        '''Fetch items.

        Args:
            count: Number of items to fetch. Defaults to 10.
        '''

No auto-fix. The mismatch could mean either the code or the docstring is
wrong; the correct resolution requires human judgement.

Only fires when:
- The parameter has a default in the signature.
- The default is a Python literal (str, int, float, bool, None). See below.
- The description contains a ``Defaults to`` phrase.
- The extracted value does not match the signature default.

Does not fire when the parameter has no default, when no ``Defaults to``
phrase is present, or when the effective default is not a literal.

## Literal-only scope and its known blind spot

DOC021 only fires when the *effective* default is a Python constant. This
excludes module-level name references such as ``SESSION_REGISTRY`` or
``DEFAULT_TIMEOUT``.

**Blind spot:** ``def foo(x=SOME_CONSTANT)`` with a docstring that says
``"Defaults to 99"`` will not fire even if ``SOME_CONSTANT != 99``. We
cannot mechanically verify the relationship between a constant name and its
value without importing the module (which docpact explicitly forbids, see
CLAUDE.md §no-imports).

**Why this is the right tradeoff:** authors routinely choose human-readable
prose over the constant name — ``"Defaults to the session registry"``
rather than ``"Defaults to SESSION_REGISTRY"``. Both are arguably correct;
firing on one forces an arbitrary choice between naming the variable and
describing it. Limiting the rule to literals eliminates all such ambiguous
cases, reduces the false-positive rate substantially on real codebases
(confirmed by an external dry-run), and keeps the rule actionable.

## FastAPI / wrapper defaults

When the signature default is a single-argument call expression like
``Query(False)`` or ``Field("hello")``, the *effective* default for
documentation purposes is the inner literal (``False`` / ``"hello"``),
not the full call expression. DOC021 extracts the inner value and compares
against it. This prevents systematic false positives on FastAPI route files.
"""

from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.rules._registry import RuleConfig, RuleMetadata, register

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo
    from docpact.model.parsed_docstring import ParsedDocstring

# Matches "Defaults to X" or "defaults to X". Captures X as:
# - A quoted string literal ('...' or "...")
# - OR a run of non-whitespace, non-comma, non-semicolon characters with
#   embedded decimal points allowed (e.g. 3.14, [], {}, True, None, 'x').
_DEFAULTS_TO_RE: re.Pattern[str] = re.compile(
    r'\bdefaults?\s+to\s+(["\'][^"\']*["\']|[^\s,;.\n]+(?:\.[^\s,;.\n]+)*)',
    re.IGNORECASE,
)


def _normalize(s: str) -> str:
    """Strip whitespace, rST backtick pairs, and one layer of matching quotes.

    Bool and None values are lowercased: Python writes ``True``/``False``/``None``
    but documentation convention across languages uses lowercase. Both sides of
    the comparison pass through here, so the case difference never fires.
    """
    s = s.strip()
    # Strip rST double-backtick markup: ``value`` → value
    if s.startswith("``") and s.endswith("``") and len(s) > 4:
        s = s[2:-2]
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1]
    if s in ("True", "False", "None"):
        return s.lower()
    return s


def _effective_default(default_str: str) -> str:
    """Return the effective default value for comparison.

    For single-argument call expressions like Query(False) or Field("x"),
    returns the unparsed inner literal. For everything else returns the
    original string unchanged.
    """
    try:
        tree = ast.parse(default_str, mode="eval")
    except SyntaxError:
        return default_str
    expr = tree.body
    if (
        isinstance(expr, ast.Call)
        and len(expr.args) == 1
        and not expr.keywords
        and isinstance(expr.args[0], ast.Constant)
    ):
        return ast.unparse(expr.args[0])
    return default_str


def _is_literal_default(default_str: str) -> bool:
    """Return True if the default string is a Python constant (str/int/float/bool/None)."""
    try:
        tree = ast.parse(default_str, mode="eval")
    except SyntaxError:
        return False
    return isinstance(tree.body, ast.Constant)


@register(
    RuleMetadata(
        code="DOC021",
        namespace="DOC",
        summary='"Defaults to X" in Args prose does not match the signature default',
        default_severity=Severity.WARNING,
        fixable=False,
        unsafe_fixable=False,
    )
)
def check(
    func: FunctionInfo,
    doc: ParsedDocstring | None,
    config: RuleConfig,
) -> list[RuleResult]:
    """Check that 'Defaults to X' phrases match the actual signature default."""
    if doc is None:
        return []

    args_section = doc.sections.get("Args")
    if args_section is None or not args_section.entries:
        return []

    param_defaults: dict[str, str] = {
        p.name: p.default for p in func.parameters if p.kind != "bound" and p.default is not None
    }

    results: list[RuleResult] = []
    loc = SourceLocation(file_path=func.file_path, line=func.line, column=func.column)

    for entry in args_section.entries:
        name = entry.key.lstrip("*")
        if name not in param_defaults:
            continue
        raw_default = param_defaults[name]
        effective = _effective_default(raw_default)
        if not _is_literal_default(effective):
            continue
        m = _DEFAULTS_TO_RE.search(entry.description)
        if m is None:
            continue
        documented = _normalize(m.group(1))
        actual = _normalize(effective)
        if documented != actual:
            results.append(
                RuleResult(
                    code="DOC021",
                    severity=config.severity,
                    message=(
                        f"Parameter {name!r}: docstring says 'Defaults to {m.group(1)}' "
                        f"but signature default is {raw_default!r}"
                    ),
                    location=loc,
                )
            )

    return results

"""Semantic docstring analysis: build prompts, call a backend, parse findings.

Backend-agnostic. Given a list of FunctionInfo (already tier-scoped by the
caller) and an LLMBackend, it renders each function as signature + docstring,
batches them within a token budget, asks the model for per-function verdicts,
and converts weak/empty verdicts into SEM001 RuleResults reusing the existing
diagnostic model and output formatters.

The check it asks for is the one the spike validated: does the docstring add
anything beyond the signature (cargo-cult), is a precondition/constraint/side
effect implied but not surfaced (hidden contract), does Returns only restate
the type (empty-returns).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from docpact.model.diagnostic import RuleResult, Severity, SourceLocation

if TYPE_CHECKING:
    from docpact.model.function_info import FunctionInfo
    from docpact.semantic.backend import LLMBackend

SYSTEM = (
    "You review Python docstrings for an agent-facing API. A docstring is GOOD only "
    "if it tells a caller something the signature and type annotations do NOT already "
    "convey: preconditions, side effects, invariants, what the return value means, "
    "what raises. "
    "Read each section in FULL before judging — judge the whole text, not its opening "
    "phrase. A Returns that names side effects, error conditions, semantics, units, or "
    "what the value means is GOOD even if it opens with the type name or 'Does not "
    "return a value'. "
    "Canonical-empty sections are correct and complete: 'Raises: None.' and "
    "'Returns: None.' state that nothing is raised / no value is returned — never flag "
    "them for failing to 'clarify' or 'explain' anything. "
    "Flag three failure modes: "
    "(1) cargo-cult — a field/return description that merely restates the name or type "
    "(e.g. 'user_id: The user id'); "
    "(2) hidden contract — a precondition, constraint, bound, or side effect implied by "
    "the code/types but absent from the prose; "
    "(3) empty-returns — a Returns whose ENTIRE body only restates the return type. "
    "Be strict but fair: a terse docstring that genuinely adds signal is GOOD. "
    "Evidence rule: for any weak/empty verdict you MUST quote, in the issue text, the "
    "exact span you judge as adding nothing beyond the name/type; if you cannot quote "
    "such a span, the verdict is good. Text that names a side effect, what is written "
    "or sent, response/status codes, units, bounds, or what the value means is signal "
    "and can NEVER be the 'adds nothing' span. "
    'Respond ONLY with JSON: {"findings":[{"name":str,"verdict":"good|weak|empty",'
    '"issues":[str,...]}]}. For any weak/empty verdict, "issues" MUST be non-empty and '
    "quote the offending span; for good, issues is empty."
)


@dataclass(frozen=True, slots=True)
class SemanticReport:
    """Outcome of a semantic run.

    Stability: beta
    """

    results: list[RuleResult]
    functions_reviewed: int
    requests: int


def _signature(func: FunctionInfo) -> str:
    """Render a compact ``def name(params) -> ret:`` line from a FunctionInfo."""
    parts: list[str] = []
    for p in func.parameters:
        if p.kind == "bound":
            parts.append(p.name)
            continue
        s = p.name
        if p.annotation:
            s += f": {p.annotation}"
        if p.default is not None:
            s += f" = {p.default}"
        parts.append(s)
    ret = f" -> {func.return_annotation}" if func.return_annotation else ""
    return f"def {func.name}({', '.join(parts)}){ret}:"


CrossfileContext = dict[tuple[str, str], str]
"""Map of (resolved-file-posix, function-name) → a cross-file contract note."""


def _context_for(func: FunctionInfo, context: CrossfileContext | None) -> str | None:
    """Return the cross-file context note for a function, or None.

    Args:
        func: The function being rendered.
        context: The cross-file context map, or None when not in --crossfile mode.

    Returns:
        The note string keyed by the function's resolved path and name, or None.
    """
    if not context:
        return None
    return context.get((func.file_path.resolve().as_posix(), func.name))


def render_function(func: FunctionInfo, context_text: str | None = None) -> str:
    """Render one function as signature + docstring text for the prompt.

    Args:
        func: The function to render.
        context_text: Optional cross-file contract note (ADR-010) appended so
            the model can judge whether the docstring documents the imported
            contract, not just the local signature.

    Returns:
        A compact ``def ...:`` line followed by the triple-quoted docstring, and
        the cross-file note when provided.

    Stability: beta
    """
    doc = (func.docstring_raw or "").strip()
    rendered = f'{_signature(func)}\n    """{doc}"""'
    if context_text:
        rendered += f"\n\n[cross-file contract] {context_text}"
    return rendered


def build_batches(
    functions: list[FunctionInfo],
    *,
    batch_chars: int = 24000,
    context: CrossfileContext | None = None,
) -> list[list[FunctionInfo]]:
    """Group functions into batches under a per-request character budget.

    Args:
        functions: Functions to review, in source order.
        batch_chars: Approximate per-request character budget (~6k tokens at
            8k-token endpoints, leaving headroom for system prompt and output).
        context: Optional cross-file context map; its notes count toward the
            per-batch size so enriched prompts still fit the budget.

    Returns:
        A list of batches, each a list of FunctionInfo whose rendered size fits
        the budget. A single oversized function still gets its own batch.

    Stability: beta
    """
    batches: list[list[FunctionInfo]] = []
    cur: list[FunctionInfo] = []
    size = 0
    for fn in functions:
        rendered = len(render_function(fn, _context_for(fn, context)))
        if cur and size + rendered > batch_chars:
            batches.append(cur)
            cur, size = [], 0
        cur.append(fn)
        size += rendered
    if cur:
        batches.append(cur)
    return batches


def user_prompt(batch: list[FunctionInfo], context: CrossfileContext | None = None) -> str:
    """Build the user message enumerating a batch of functions to review.

    Args:
        batch: The functions in this request.
        context: Optional cross-file context map (ADR-010) for prompt enrichment.

    Returns:
        A single user-message string.

    Stability: beta
    """
    body = "\n\n---\n\n".join(render_function(fn, _context_for(fn, context)) for fn in batch)
    return f"Review these {len(batch)} functions. Return JSON only.\n\n{body}"


def _extract_json(content: str) -> dict:
    """Parse a model reply as JSON, tolerating markdown fences or surrounding prose."""
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`").lstrip("json").strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end > start:
            return json.loads(content[start : end + 1])
        raise


# Verdict severity rank, ascending. A verdict surfaces as a finding only when
# its rank is at least the configured finding_threshold's rank (config §15.1).
# "good" is absent — it never produces a finding.
_VERDICT_RANK = {"weak": 0, "empty": 1}


def analyze(
    functions: list[FunctionInfo],
    backend: LLMBackend,
    *,
    severity: Severity = Severity.WARNING,
    threshold: str = "weak",
    context: CrossfileContext | None = None,
) -> SemanticReport:
    """Run semantic analysis over tier-scoped functions and return SEM001 findings.

    Args:
        functions: Functions to review (the caller scopes these by tier).
        backend: The LLM backend to call.
        severity: Severity to attach to emitted SEM001 results.
        threshold: Least-severe verdict that surfaces as a finding — ``"weak"``
            (default) surfaces both ``weak`` and ``empty``; ``"empty"`` surfaces
            only ``empty``. Verdicts ranking below the threshold are dropped.
        context: Optional cross-file context map (ADR-010); when provided, a
            function's resolved input-model fields and registry description are
            appended to its prompt so the model judges the full cross-file
            contract.

    Returns:
        A SemanticReport with one SEM001 RuleResult per surfaced verdict (good
        verdicts, and verdicts below ``threshold``, produce nothing), plus the
        counts of functions reviewed and requests made.

    Raises:
        SemanticError: A backend call failed (propagated from the backend).

    Constraints:
        Non-deterministic: results may vary across model versions. Advisory
        only — never used to gate `check`. A batch whose reply cannot be parsed
        as JSON is skipped (no findings) rather than aborting the run.

    Stability: beta
    """
    by_name: dict[str, FunctionInfo] = {}
    for fn in functions:
        by_name.setdefault(fn.name, fn)

    min_rank = _VERDICT_RANK.get(threshold, 0)
    results: list[RuleResult] = []
    batches = build_batches(functions, context=context)
    for batch in batches:
        reply = backend.complete(SYSTEM, user_prompt(batch, context))
        try:
            parsed = _extract_json(reply)
        except json.JSONDecodeError:
            continue  # advisory: skip an unparseable batch rather than fail
        for finding in parsed.get("findings", []):
            verdict = finding.get("verdict")
            if verdict not in _VERDICT_RANK or _VERDICT_RANK[verdict] < min_rank:
                continue
            fn = by_name.get(finding.get("name", ""))
            if fn is None:
                continue
            issues = "; ".join(finding.get("issues", [])) or "weak docstring"
            results.append(
                RuleResult(
                    code="SEM001",
                    severity=severity,
                    message=f"{verdict}: {issues}",
                    location=SourceLocation(file_path=fn.file_path, line=fn.line, column=fn.column),
                )
            )

    results.sort(key=lambda r: (str(r.location.file_path), r.location.line, r.location.column))
    return SemanticReport(results=results, functions_reviewed=len(functions), requests=len(batches))

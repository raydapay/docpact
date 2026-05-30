"""SPIKE — semantic docstring check via GitHub Models. THROWAWAY, not shipped.

Purpose: read the *signal quality* of an LLM-based semantic docstring check before
deciding whether to build the SEM layer (spec §12.2). It is deliberately NOT wired
into the package, the CLI, tests, or `make verify` — it lives in scripts/ and is
meant to be deleted (or graduated into a real `docpact semantic`) after we look at
its output.

It reuses docpact's own parser (extract_functions + the model types), which is the
point: a real SEM mode would sit on top of the same per-file FunctionInfo +
ParsedDocstring the rules already consume. The LLM never sees the repo — only the
batched (signature + docstring) text we send.

What it asks the model: for each function, does the docstring tell a caller/agent
anything beyond what the signature and type annotations already say? It flags
(1) cargo-cult restatement, (2) preconditions/constraints/side-effects implied but
not surfaced in prose, (3) a Returns that merely restates the return type.

Batching: GitHub Models free tier is ~50–150 requests/day with 8k input tokens per
request. We pack many functions per request, so the whole corpus is a few requests.

Usage:
    export GITHUB_TOKEN=<PAT with models:read scope>
    uv run python scripts/spike_semantic.py src/docpact --limit 40
    uv run python scripts/spike_semantic.py src/docpact --dry-run   # no API call

Endpoint / model are overridable via env (GH_MODELS_ENDPOINT, GH_MODELS_MODEL) since
GitHub Models endpoints have shifted over time. Defaults target the current
OpenAI-compatible endpoint; the older Azure-flavored one is noted below.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from docpact.parser.source import extract_functions  # noqa: E402
from docpact.tiers import assign_tier  # noqa: E402

# OpenAI-compatible chat-completions endpoint. Current GitHub Models surface uses
# publisher/model IDs (e.g. "openai/gpt-4o-mini"). If this 404s, try the older
# Azure-flavored endpoint "https://models.inference.ai.azure.com/chat/completions"
# with a bare model id ("gpt-4o-mini").
ENDPOINT = os.environ.get("GH_MODELS_ENDPOINT", "https://models.github.ai/inference/chat/completions")
MODEL = os.environ.get("GH_MODELS_MODEL", "openai/gpt-4o-mini")  # low-tier → 150 req/day free

_SYSTEM = (
    "You review Python docstrings for an agent-facing API. A docstring is GOOD only "
    "if it tells a caller something the signature and type annotations do NOT already "
    "convey: preconditions, side effects, invariants, what the return value means, "
    "what raises. Flag three failure modes: "
    "(1) cargo-cult — a field/return description that merely restates the name or type "
    "(e.g. 'user_id: The user id'); "
    "(2) hidden contract — a precondition, constraint, bound, or side effect implied by "
    "the code/types but absent from the prose; "
    "(3) empty-returns — a Returns that only restates the return type. "
    "Be strict but fair: a terse docstring that genuinely adds signal is GOOD. "
    'Respond ONLY with JSON: {"findings":[{"name":str,"verdict":"good|weak|empty",'
    '"issues":[str,...]}]}. For any weak/empty verdict, "issues" MUST be non-empty and '
    "name the specific missing information; for good, issues is empty."
)

# Planted examples so we can read precision AND recall at a glance: the cargo-cult
# and hidden-constraint ones SHOULD be flagged; the good one should NOT.
_PLANTED: list[str] = [
    'def process(user_id: str, flags: int) -> dict:\n'
    '    """Process.\n\n    Args:\n        user_id: The user id.\n        flags: The flags.\n\n'
    '    Returns:\n        The result.\n    """  # PLANTED: cargo-cult, expect verdict=empty/weak',
    'def withdraw(account_id: str, amount_cents: int) -> Receipt:\n'
    '    """Withdraw funds from an account.\n\n    Args:\n        account_id: Account to debit.\n'
    '        amount_cents: Amount in cents.\n\n    Returns:\n        A receipt.\n    """'
    '  # PLANTED: hidden contract (must be > 0, must not overdraw, side effect) expect weak',
    'def find_orders(query: str, limit: int = 10) -> list[Order]:\n'
    '    """Find orders by SKU, customer name, or email.\n\n    Args:\n        query: SKU, customer\n'
    '            name, or email; matched as a partial against four indexed columns.\n'
    '        limit: Max rows; capped at 10 server-side even if a larger value is passed.\n\n'
    '    Returns:\n        Orders ordered by most-recent activity; empty list if none match.\n'
    '    """  # PLANTED: genuinely useful, expect verdict=good',
]


def _signature(func: object) -> str:
    """Render a compact `def name(params) -> ret` line from a FunctionInfo."""
    parts: list[str] = []
    for p in func.parameters:  # type: ignore[attr-defined]
        if p.kind == "bound":
            parts.append(p.name)
            continue
        s = p.name
        if p.annotation:
            s += f": {p.annotation}"
        if p.default is not None:
            s += f" = {p.default}"
        parts.append(s)
    ret = f" -> {func.return_annotation}" if func.return_annotation else ""  # type: ignore[attr-defined]
    return f"def {func.name}({', '.join(parts)}){ret}:"  # type: ignore[attr-defined]


def _render(func: object) -> str:
    """Render one function as `signature + docstring` text for the prompt."""
    doc = func.docstring_raw or ""  # type: ignore[attr-defined]
    return f'{_signature(func)}\n    """{doc.strip()}"""'


def _collect(root: Path, limit: int, min_tier: int) -> list[str]:
    """Collect rendered tool-ish functions: docstring, ≥1 real param, tier ≥ min_tier.

    The tier filter matters — SEM mode would target agent-facing functions, not
    Tier-1 internal helpers that docpact intentionally lets stay terse.
    """
    out: list[str] = []
    files = [root] if root.is_file() else sorted(root.rglob("*.py"))
    for f in files:
        try:
            funcs = extract_functions(f)
        except SyntaxError:
            continue
        for fn in funcs:
            if fn.docstring_raw is None:
                continue
            real = [p for p in fn.parameters if p.kind in ("positional", "keyword")]
            if not real:
                continue
            if assign_tier(fn) < min_tier:
                continue
            out.append(_render(fn))
            if len(out) >= limit:
                return out
    return out


def _batch(items: list[str], budget_chars: int = 24000) -> list[list[str]]:
    """Pack rendered functions into batches under a per-request char budget (~6k tokens)."""
    batches: list[list[str]] = []
    cur: list[str] = []
    size = 0
    for it in items:
        if cur and size + len(it) > budget_chars:
            batches.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += len(it)
    if cur:
        batches.append(cur)
    return batches


def _user_prompt(batch: list[str]) -> str:
    """Build the user message: numbered functions to review."""
    body = "\n\n---\n\n".join(batch)
    return f"Review these {len(batch)} functions. Return JSON only.\n\n{body}"


class _SpikeError(Exception):
    """A batch-level failure: reported, but does not abort the whole run."""


def _extract_json(content: str) -> dict:
    """Parse the model's JSON reply, tolerating markdown fences or surrounding prose."""
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


def _call(token: str, batch: list[str], timeout: float = 90.0) -> dict:
    """POST one batch to GitHub Models; return parsed findings (with _usage).

    Raises _SpikeError with a human-readable cause on any HTTP / network /
    response-shape / JSON failure, so the caller can report it and continue.
    """
    payload = {
        "model": MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _user_prompt(batch)},
        ],
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        if e.code == 429:
            raise _SpikeError(f"rate-limited (HTTP 429) — minute/day cap hit. {detail}") from e
        if e.code in (401, 403):
            raise _SpikeError(f"auth (HTTP {e.code}) — PAT needs models:read. {detail}") from e
        raise _SpikeError(f"HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise _SpikeError(f"network/transport error: {e}") from e
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise _SpikeError(f"unexpected response shape: {json.dumps(body)[:300]}") from e
    try:
        parsed = _extract_json(content)
    except json.JSONDecodeError as e:
        raise _SpikeError(f"model returned non-JSON: {content[:300]}") from e
    parsed["_usage"] = body.get("usage", {})
    return parsed


def main(argv: list[str] | None = None) -> int:
    """Run the semantic-check spike over a path and print findings + cost."""
    p = argparse.ArgumentParser(description="SPIKE: semantic docstring check via GitHub Models")
    p.add_argument("path", type=Path, help="Directory/file to scan (e.g. src/docpact)")
    p.add_argument("--limit", type=int, default=40, help="Max functions to review (default 40)")
    p.add_argument("--min-tier", type=int, default=2, help="Only review functions at this tier or higher (default 2 — skips Tier-1 internals)")
    p.add_argument("--dry-run", action="store_true", help="Print prompts; make no API call")
    p.add_argument("--no-planted", action="store_true", help="Omit the 3 planted sanity examples")
    args = p.parse_args(argv)

    items = ([] if args.no_planted else list(_PLANTED)) + _collect(args.path, args.limit, args.min_tier)
    if not items:
        print("No functions with docstrings + params found.")
        return 1
    batches = _batch(items)
    print(f"{len(items)} functions → {len(batches)} request(s)  (model={MODEL})\n")

    if args.dry_run:
        for i, b in enumerate(batches, 1):
            print(f"===== REQUEST {i}/{len(batches)} ({len(b)} functions) =====")
            print(_user_prompt(b))
            print()
        print("Dry run — no API call, no data sent.")
        return 0

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("error: set GITHUB_TOKEN (PAT with models:read) to call the API.", file=sys.stderr)
        return 2

    import time

    total_in = total_out = 0
    failures = 0
    by_verdict: dict[str, int] = {"good": 0, "weak": 0, "empty": 0}
    for i, b in enumerate(batches, 1):
        print(f"  request {i}/{len(batches)} ({len(b)} functions) ... ", end="", flush=True)
        t0 = time.perf_counter()
        try:
            result = _call(token, b)
        except _SpikeError as e:
            print("FAILED")
            print(f"    {e}", file=sys.stderr)
            failures += 1
            continue
        print(f"{time.perf_counter() - t0:.1f}s")
        usage = result.get("_usage", {})
        total_in += usage.get("prompt_tokens", 0)
        total_out += usage.get("completion_tokens", 0)
        for fnd in result.get("findings", []):
            v = fnd.get("verdict", "?")
            by_verdict[v] = by_verdict.get(v, 0) + 1
            marker = {"good": "  ok", "weak": "WEAK", "empty": "EMPTY"}.get(v, v.upper())
            print(f"  [{marker}] {fnd.get('name', '?')}")
            for issue in fnd.get("issues", []):
                print(f"           - {issue}")

    print(f"\nverdicts: {by_verdict}")
    print(f"tokens: {total_in} in / {total_out} out across {len(batches) - failures} ok request(s)")
    if failures:
        print(f"{failures} request(s) failed (see stderr above).")
    print("(free tier: ~150 low-tier requests/day — this run cost the above)")
    return 3 if failures and not any(by_verdict.values()) else 0


if __name__ == "__main__":
    sys.exit(main())

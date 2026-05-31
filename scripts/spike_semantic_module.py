"""Throwaway spike: is module-level SEM a reliable, low-FP signal?

Run BEFORE building module-level scan (the discipline ADR-008 set for the
function-level spike). It does NOT re-prove "can an LLM judge docstrings" — that
is settled. It answers the three open questions the function spike did not:

  1. FALSE-POSITIVE RATE on real, decent module docstrings (docpact's own src/).
     A module-level rule is only worth building if known-good modules come back
     mostly "good". This is the build / don't-build gate.

  2. INPUT SHAPE. Three variants per module — docstring ALONE, docstring + the
     module's public SYMBOLS, docstring + symbols + project CONTEXT (README etc.).
     The cheapest variant that still produces signal tells us what we must feed
     the model (and therefore the token cost and architecture).

  3. RUBRIC. Two dimensions judged separately: SCOPE (factual — does the docstring
     match what the module actually contains?) and ORIENTATION (subjective — does
     it help a reader choose this module vs. siblings?). The hypothesis is that
     SCOPE survives (low FP) and ORIENTATION is a taste-driven FP magnet. The
     spike shows which dimension to ship and which to drop.

Read the outcome like this:
  - SCOPE flags ~0 of the known-good docpact modules and catches the planted-bad
    ones  -> ship a scope-only module rule, with the cheapest input variant that
    worked.
  - ORIENTATION flags a chunk of known-good modules ("not orienting enough")
    -> drop the orientation dimension (it is taste, not drift).
  - Even SCOPE is noisy on known-good modules, or needs the full-context variant
    to be useful -> don't build module-level, or radically narrow it.

Usage (needs a real backend; uses the same config path as `docpact semantic`):

    GITHUB_TOKEN=... uv run python scripts/spike_semantic_module.py \
        --api-base https://models.github.ai/inference --model openai/gpt-4o-mini

    # inspect the prompts without spending a token:
    uv run python scripts/spike_semantic_module.py --dry-run

Not shipped; delete once the build/don't-build decision is recorded. Mirrors the
since-removed scripts/spike_semantic.py.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_SYSTEM = """You audit whether a Python MODULE docstring orients a reader correctly.

Judge two dimensions independently. For each, return "good" or "weak", and for
"weak" you MUST quote the exact offending span — if you cannot quote a span, the
verdict is "good".

- scope: does the docstring's description match what the module ACTUALLY contains
  (the listed public symbols)? "weak" only if it claims something not present, or
  omits the module's evident main purpose. A terse-but-accurate summary is good.
- orientation: does it help a reader decide WHEN/WHY to use this module rather
  than guess? "weak" only if it is contentless boilerplate (e.g. just restates the
  filename). Do NOT flag a docstring merely for being brief, or for not comparing
  itself to other modules.

Be fair, not pedantic. Most real module docstrings are good. Reply ONLY with JSON:
{"scope": "good|weak", "scope_evidence": "...", "orientation": "good|weak", "orientation_evidence": "..."}
"""


@dataclass
class Unit:
    """One module under audit."""

    label: str
    docstring: str
    symbols: list[str]  # "name — first line of its docstring"


# Planted-bad module docstrings: a module-level rule SHOULD catch these.
_PLANTED: list[Unit] = [
    Unit(
        label="planted: generic boilerplate",
        docstring="Utilities.",
        symbols=["parse_config — Load and validate a pyproject.toml.", "Config — Resolved settings."],
    ),
    Unit(
        label="planted: scope mismatch (claims what isn't there)",
        docstring="HTTP client and connection pooling for the payments gateway.",
        symbols=["format_date — Render a date as ISO-8601.", "slugify — Make a URL-safe slug."],
    ),
    Unit(
        label="planted: just restates the filename",
        docstring="The widgets module.",
        symbols=["Widget — A UI widget.", "render — Draw a widget tree to the terminal."],
    ),
]


def _public_symbols(tree: ast.Module) -> list[str]:
    """Return 'name — summary' for each public top-level def/class."""
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                continue
            doc = ast.get_docstring(node) or ""
            summary = doc.strip().splitlines()[0] if doc.strip() else "(no docstring)"
            out.append(f"{node.name} — {summary}")
    return out


def _collect(paths: list[Path]) -> list[Unit]:
    """Collect real module docstrings + public symbols from .py files under paths."""
    units: list[Unit] = []
    files: list[Path] = []
    for p in paths:
        files.extend(sorted(p.rglob("*.py")) if p.is_dir() else [p])
    for f in files:
        if f.name == "__init__.py":
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        doc = ast.get_docstring(tree)
        if not doc:
            continue  # DOC002's job, not SEM's
        units.append(Unit(label=str(f), docstring=doc, symbols=_public_symbols(tree)))
    return units


def _prompt(unit: Unit, variant: str, context: str) -> str:
    """Build the user prompt for one unit under one input variant."""
    parts = [f"Module docstring:\n\"\"\"\n{unit.docstring}\n\"\"\""]
    if variant in ("symbols", "context"):
        listed = "\n".join(f"  - {s}" for s in unit.symbols) or "  (none)"
        parts.append(f"Public symbols actually defined in the module:\n{listed}")
    if variant == "context" and context:
        parts.append(f"Project context (for orientation):\n{context[:2000]}")
    return "\n\n".join(parts)


def _complete(api_base: str, model: str, key: str, system: str, user: str, timeout: float) -> str:
    """One chat-completions call (openai-compat), returning the message content."""
    body = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
    ).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 - fixed https endpoint from config
        f"{api_base.rstrip('/')}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        payload = json.loads(resp.read())
    return payload["choices"][0]["message"]["content"]


def _parse(reply: str) -> dict:
    """Tolerantly extract the JSON verdict object from a reply."""
    text = reply.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].removeprefix("json").strip()
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1]) if start != -1 else {}


def main() -> int:
    """Run the module-level SEM spike across input variants and rubric dimensions."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="*", default=["src/docpact"], help="dirs/files of real modules")
    ap.add_argument("--api-base", default=os.environ.get("DOCPACT_SPIKE_API_BASE", ""))
    ap.add_argument("--model", default=os.environ.get("DOCPACT_SPIKE_MODEL", "openai/gpt-4o-mini"))
    ap.add_argument("--api-key-env", default="GITHUB_TOKEN")
    ap.add_argument("--variant", choices=["alone", "symbols", "context", "all"], default="all")
    ap.add_argument("--context-files", nargs="*", default=["README.md", "CLAUDE.md"])
    ap.add_argument("--limit", type=int, default=20, help="cap real modules sampled (cost)")
    ap.add_argument("--dry-run", action="store_true", help="print prompts; no API call")
    args = ap.parse_args()

    real = _collect([Path(p) for p in args.paths])[: args.limit]
    units = [(u, "known-good") for u in real] + [(u, "planted-bad") for u in _PLANTED]
    context = "\n".join(
        Path(c).read_text(encoding="utf-8") for c in args.context_files if Path(c).exists()
    )
    variants = ["alone", "symbols", "context"] if args.variant == "all" else [args.variant]

    print(f"{len(real)} real module(s) + {len(_PLANTED)} planted; variants={variants}\n")

    if args.dry_run:
        u = units[0][0]
        print(f"=== SYSTEM ===\n{_SYSTEM}")
        for v in variants:
            print(f"\n=== USER ({v}) — {u.label} ===\n{_prompt(u, v, context)}")
        print("\nDry run — no API call.")
        return 0

    if not args.api_base:
        print("error: --api-base required (or set DOCPACT_SPIKE_API_BASE)", file=sys.stderr)
        return 2
    key = os.environ.get(args.api_key_env, "")
    if not key:
        print(f"error: {args.api_key_env} is not set", file=sys.stderr)
        return 2

    # tally[variant][cohort][dimension] = [weak_count, total]
    tally: dict[str, dict[str, dict[str, list[int]]]] = {}
    for v in variants:
        for u, cohort in units:
            try:
                reply = _complete(args.api_base, args.model, key, _SYSTEM, _prompt(u, v, context), 90)
                verdict = _parse(reply)
            except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
                print(f"  [skip] {v} {u.label}: {exc}")
                continue
            for dim in ("scope", "orientation"):
                slot = tally.setdefault(v, {}).setdefault(cohort, {}).setdefault(dim, [0, 0])
                slot[1] += 1
                if verdict.get(dim) == "weak":
                    slot[0] += 1
                    ev = verdict.get(f"{dim}_evidence", "")
                    print(f"  [{v}|{cohort}|{dim}=weak] {u.label}: {ev}")

    print("\n=== SUMMARY (weak / total) — FP = weak on known-good; recall = weak on planted-bad ===")
    for v in variants:
        for cohort in ("known-good", "planted-bad"):
            for dim in ("scope", "orientation"):
                w, t = tally.get(v, {}).get(cohort, {}).get(dim, [0, 0])
                print(f"  {v:8} {cohort:11} {dim:11} {w}/{t}")
    print("\nDecision: ship the dimension(s) with ~0 FP on known-good AND catches on planted-bad,")
    print("at the cheapest variant that achieves it. If only 'context' works, weigh the cost.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

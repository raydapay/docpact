"""Sync the test-count and coverage line in README.md with the current suite.

Run from the project root:

    uv run python scripts/update_readme_stats.py           # update in-place
    uv run python scripts/update_readme_stats.py --check   # exit 1 if stale

The script reads the cached .coverage file (produced by ``make coverage``)
for the coverage percentage, and collects the test count via
``pytest --collect-only`` (fast, no execution). Both calls are cheap after
a normal ``make coverage`` run.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

README = Path(__file__).parent.parent / "README.md"
_STATS_RE = re.compile(r"\d+ tests, \d+% coverage")


def _test_count() -> int:
    """Count collected tests without running them."""
    result = subprocess.run(
        ["uv", "run", "pytest", "--collect-only", "-q", "--no-header"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    for line in reversed(result.stdout.splitlines()):
        m = re.search(r"(\d+) tests? collected", line)
        if m:
            return int(m.group(1))
    raise RuntimeError(f"Could not parse test count:\n{result.stdout}{result.stderr}")


def _coverage_pct() -> int:
    """Read the total coverage percentage from the cached .coverage file."""
    result = subprocess.run(
        ["uv", "run", "coverage", "report"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    for line in result.stdout.splitlines():
        if line.startswith("TOTAL"):
            pct_str = line.split()[-1].rstrip("%")
            return int(float(pct_str))
    raise RuntimeError(f"Could not parse coverage total:\n{result.stdout}{result.stderr}")


def main() -> None:
    """Update or verify the stats line in README.md."""
    check_only = "--check" in sys.argv

    count = _test_count()
    pct = _coverage_pct()
    expected = f"{count} tests, {pct}% coverage"

    text = README.read_text(encoding="utf-8")
    m = _STATS_RE.search(text)
    if m is None:
        print(f"error: stats pattern not found in README.md (expected: {_STATS_RE.pattern})")
        sys.exit(1)

    current = m.group(0)
    if current == expected:
        print(f"README.md stats are current: {expected}")
        return

    if check_only:
        print("README.md stats are stale:")
        print(f"  current:  {current}")
        print(f"  expected: {expected}")
        sys.exit(1)

    README.write_text(_STATS_RE.sub(expected, text), encoding="utf-8")
    print(f"README.md: {current!r} → {expected!r}")


if __name__ == "__main__":
    main()

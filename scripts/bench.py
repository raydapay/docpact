"""Performance benchmark — pre-commit guard against throughput regressions.

Runs _run_checks on the project's own source and test fixtures, takes a
trimmed mean (default: 20 runs, drop slowest and fastest), reports
functions/sec, and compares against a machine-local baseline.

Metric is functions/sec rather than wall time so that adding new fixture
files or source files does not invalidate the baseline.

Run from the project root:

    uv run python scripts/bench.py              # compare against baseline
    uv run python scripts/bench.py --update     # save current result as baseline
    uv run python scripts/bench.py --threshold 0.10  # 10% regression threshold

The baseline is stored in .bench_baseline.json (gitignored, machine-local).
First run writes the baseline and exits 0. Subsequent runs compare and exit 1
on regression.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
BASELINE_PATH = ROOT / ".bench_baseline.json"

# Corpus: project source + fixtures.  Both grow with new rules (fixtures are
# required per CLAUDE.md for every new rule), so throughput automatically
# accounts for new rule overhead without any manual update.
CORPUS_DIRS = [ROOT / "src" / "docpact", ROOT / "tests" / "fixtures"]

sys.path.insert(0, str(ROOT / "src"))

# Importing _run_checks from cli intentionally — it is the hot path we are
# measuring.  Pulling it in here avoids subprocess overhead that would add
# ~100 ms of interpreter startup noise to every run.
from docpact.cli import _run_checks  # noqa: E402
from docpact.config import load_config  # noqa: E402
from docpact.parser.source import extract_functions  # noqa: E402
from docpact.rules import load_builtin_rules  # noqa: E402

load_builtin_rules()


def _collect_corpus() -> list[Path]:
    files: list[Path] = []
    for d in CORPUS_DIRS:
        if d.exists():
            files.extend(sorted(d.rglob("*.py")))
    return files


def _count_functions(corpus: list[Path]) -> int:
    return sum(len(extract_functions(f)) for f in corpus)


def _timed_run(corpus: list[Path], config: object) -> float:
    start = time.perf_counter()
    _run_checks(corpus, config)  # type: ignore[arg-type]
    return time.perf_counter() - start


def _trimmed_mean(times: list[float]) -> float:
    s = sorted(times)
    return statistics.mean(s[1:-1])


def main(argv: list[str] | None = None) -> int:
    """Run the benchmark and compare against the stored baseline.

    Args:
        argv: Argument list; defaults to sys.argv when None.

    Returns:
        0 on success or first-run baseline write; 1 on regression.
    """
    p = argparse.ArgumentParser(description="docpact throughput benchmark")
    p.add_argument(
        "--threshold",
        type=float,
        default=0.05,
        metavar="FRAC",
        help="Regression threshold as a fraction (default: 0.05 = 5%%)",
    )
    p.add_argument(
        "--runs",
        type=int,
        default=20,
        metavar="N",
        help="Number of timed runs (default: 20; minimum 3)",
    )
    p.add_argument(
        "--update",
        action="store_true",
        help="Replace the stored baseline with the current result",
    )
    args = p.parse_args(argv)

    if args.runs < 3:
        print("error: --runs must be at least 3 (trimming requires min and max)")
        return 1

    corpus = _collect_corpus()
    if not corpus:
        print("error: no Python files found in corpus directories")
        return 1

    config = load_config(ROOT)
    func_count = _count_functions(corpus)

    print(f"docpact bench  —  {args.runs} runs, drop min/max, trimmed mean")
    print(f"corpus: {len(corpus)} files, {func_count} functions")
    print()

    # One warm-up run: avoids cold filesystem-cache and import-cache effects
    # that would inflate the first timed measurement.
    _run_checks(corpus, config)  # type: ignore[arg-type]

    times = [_timed_run(corpus, config) for _ in range(args.runs)]
    s = sorted(times)
    trimmed = s[1:-1]
    mean_s = statistics.mean(trimmed)
    stdev_s = statistics.stdev(trimmed) if len(trimmed) > 1 else 0.0
    cv_pct = (stdev_s / mean_s) * 100 if mean_s else 0.0
    throughput = func_count / mean_s

    print(f"  excluded  min={s[0]*1000:.1f}ms  max={s[-1]*1000:.1f}ms")
    print(f"  mean={mean_s*1000:.1f}ms  σ={stdev_s*1000:.1f}ms  cv={cv_pct:.1f}%")
    print(f"  throughput: {throughput:.0f} fn/s")

    if cv_pct > 10:
        print(f"  warning: high variance (cv={cv_pct:.1f}%) — environment may be noisy")

    print()

    current = {
        "throughput_fn_s": throughput,
        "mean_ms": mean_s * 1000,
        "corpus_files": len(corpus),
        "func_count": func_count,
        "runs": args.runs,
    }

    if args.update or not BASELINE_PATH.exists():
        BASELINE_PATH.write_text(json.dumps(current, indent=2) + "\n")
        label = "updated" if args.update else "written"
        print(f"baseline {label}: {BASELINE_PATH.name}")
        return 0

    baseline = json.loads(BASELINE_PATH.read_text())
    baseline_tput = baseline["throughput_fn_s"]
    delta = (throughput - baseline_tput) / baseline_tput  # positive = faster

    symbol = f"+{delta*100:.1f}%" if delta >= 0 else f"{delta*100:.1f}%"
    print(f"baseline: {baseline_tput:.0f} fn/s")
    print(f"current:  {throughput:.0f} fn/s  ({symbol})")

    if delta < -args.threshold:
        print()
        print(
            f"REGRESSION: {abs(delta)*100:.1f}% slower than baseline"
            f" (threshold: {args.threshold*100:.0f}%)"
        )
        print("Run 'make bench-update' after confirming the change is intentional.")
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

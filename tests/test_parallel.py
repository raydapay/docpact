"""Tests for parallel file analysis and the `docpact bench` command (ADR-006 item 5)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from docpact.cli import _resolve_jobs, _run_checks, main
from docpact.config import Config

# A small multi-file corpus with a mix of clean and violating docstrings, so the
# serial/parallel equivalence test exercises real diagnostics, not just empty runs.
_FILES = {
    "a.py": '''"""Module a."""


def alpha(x: int) -> int:
    """Do alpha.

    Args:
        x: A number.

    Returns:
        It.
    """
    return x
''',
    "b.py": '''"""Module b."""


def beta(name, value):
    return name
''',
    "c.py": "def gamma(:\n",  # syntax error -> PARSE001 path in a worker
}


def _write_corpus(root: Path) -> list[Path]:
    """Write the corpus files under root and return their paths in name order."""
    paths = []
    for name, src in sorted(_FILES.items()):
        p = root / name
        p.write_text(src)
        paths.append(p)
    return paths


def _diag_keys(results: list) -> list[tuple]:
    """Reduce diagnostics to comparable (path, line, col, code) tuples."""
    return [
        (str(r.location.file_path), r.location.line, r.location.column, r.code) for r in results
    ]


def test_parallel_matches_serial(tmp_path: Path) -> None:
    files = _write_corpus(tmp_path)
    cfg_serial = Config(select=("DOC", "PARSE"), jobs=1)
    cfg_parallel = Config(select=("DOC", "PARSE"), jobs=2)

    serial, _ = _run_checks(files, cfg_serial, tmp_path)
    parallel, _ = _run_checks(files, cfg_parallel, tmp_path)

    # Identical diagnostics regardless of worker count — determinism holds.
    assert _diag_keys(serial) == _diag_keys(parallel)
    assert serial  # the corpus does produce violations


def test_parallel_suppression_maps_match(tmp_path: Path) -> None:
    files = _write_corpus(tmp_path)
    _, sup_serial = _run_checks(files, Config(select=("DOC", "PARSE"), jobs=1), tmp_path)
    _, sup_parallel = _run_checks(files, Config(select=("DOC", "PARSE"), jobs=2), tmp_path)
    assert set(sup_serial) == set(sup_parallel)


def test_resolve_jobs() -> None:
    assert _resolve_jobs(1) == 1
    assert _resolve_jobs(4) == 4
    assert _resolve_jobs(0) >= 1  # auto -> at least one
    assert _resolve_jobs(-5) == 1  # defensive clamp


def test_check_jobs_flag_runs(tmp_path: Path) -> None:
    _write_corpus(tmp_path)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        Path(td, "m.py").write_text('"""M."""\n\n\ndef f(a):\n    return a\n')
        result = runner.invoke(main, ["check", "m.py", "--jobs", "2", "--select", "DOC"])
    assert result.exit_code in (0, 1)  # ran without crashing


def test_bench_command_runs(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        for name, src in _FILES.items():
            if name != "c.py":  # skip the syntax-error file for a clean bench
                Path(td, name).write_text(src)
        result = runner.invoke(main, ["bench", ".", "--runs", "1", "--jobs", "2"])
    assert result.exit_code == 0
    assert "docpact bench" in result.output
    assert "speedup:" in result.output
    assert "Recommendation:" in result.output


def test_bench_no_files_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        Path(td, "empty").mkdir()
        result = runner.invoke(main, ["bench", "empty"])
    assert result.exit_code != 0

"""Tests for DOC052 — Examples section absent when require_examples_min_tier is set."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from docpact.fix import apply_fixes
from docpact.model.diagnostic import Severity
from docpact.model.function_info import FunctionInfo
from docpact.model.parsed_docstring import ParsedDocstring, Section
from docpact.parser.source import extract_functions
from docpact.rules._registry import RuleConfig, all_rules
from docpact.rules.doc.doc052_missing_examples import check


def _func(path: Path, docstring_end_offset: int = 50) -> FunctionInfo:
    return FunctionInfo(
        name="foo",
        file_path=path,
        line=1,
        column=0,
        parameters=(),
        return_annotation=None,
        decorators=(),
        docstring_raw='"""Summary."""',
        docstring_line=2,
        containing_class=None,
        def_start_offset=0,
        def_end_offset=20,
        docstring_start_offset=20,
        docstring_end_offset=docstring_end_offset,
    )


def _doc(with_examples: bool = False) -> ParsedDocstring:
    sections = {"Examples": Section(name="Examples", body="x = foo()")} if with_examples else {}
    return ParsedDocstring(summary="Summary.", description=None, sections=sections, raw="Summary.")


def _cfg(tier: int, min_tier: int | None) -> RuleConfig:
    return RuleConfig(
        severity=Severity.ERROR,
        options={"tier": tier, "require_examples_min_tier": min_tier},
    )


# ---------------------------------------------------------------------------
# Opt-in guard: rule is silent when require_examples_min_tier is not set
# ---------------------------------------------------------------------------


def test_no_min_tier_set_returns_empty(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    assert check(func, _doc(), _cfg(tier=3, min_tier=None)) == []


def test_no_docstring_returns_empty(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    assert check(func, None, _cfg(tier=3, min_tier=3)) == []


# ---------------------------------------------------------------------------
# Tier threshold
# ---------------------------------------------------------------------------


def test_tier_below_threshold_returns_empty(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    assert check(func, _doc(), _cfg(tier=2, min_tier=3)) == []


def test_tier_at_threshold_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    results = check(func, _doc(), _cfg(tier=3, min_tier=3))
    assert len(results) == 1
    assert results[0].code == "DOC052"


def test_tier_above_threshold_fires(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    results = check(func, _doc(), _cfg(tier=4, min_tier=3))
    assert len(results) == 1
    assert results[0].code == "DOC052"


def test_threshold_2_fires_at_tier_2(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    results = check(func, _doc(), _cfg(tier=2, min_tier=2))
    assert len(results) == 1


def test_threshold_2_silent_at_tier_1(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    assert check(func, _doc(), _cfg(tier=1, min_tier=2)) == []


# ---------------------------------------------------------------------------
# Examples section already present → no violation
# ---------------------------------------------------------------------------


def test_examples_present_returns_empty(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    assert check(func, _doc(with_examples=True), _cfg(tier=3, min_tier=3)) == []


# ---------------------------------------------------------------------------
# Fix: attached, positioned, content
# ---------------------------------------------------------------------------


def test_fix_is_attached(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    results = check(func, _doc(), _cfg(tier=3, min_tier=3))
    assert results[0].fix is not None


def test_fix_start_is_before_closing_quotes(tmp_path: Path) -> None:
    end = 50
    func = _func(tmp_path / "t.py", docstring_end_offset=end)
    results = check(func, _doc(), _cfg(tier=3, min_tier=3))
    fix = results[0].fix
    assert fix is not None
    assert fix.start_offset == end - 3
    assert fix.end_offset == end


def test_fix_replacement_contains_examples_and_fill(tmp_path: Path) -> None:
    func = _func(tmp_path / "t.py")
    results = check(func, _doc(), _cfg(tier=3, min_tier=3))
    replacement = results[0].fix.replacement  # type: ignore[union-attr]
    assert "Examples:" in replacement
    assert "[FILL]" in replacement
    assert '"""' in replacement


# ---------------------------------------------------------------------------
# Integration: fix produces valid output on a real file
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        # Multi-line docstring
        '"""Summary.\n\nArgs:\n    x: blah\n"""\n',
        # Single-line docstring
        '"""Summary."""\n',
    ],
)
def test_fix_applied_adds_examples_section(tmp_path: Path, source: str) -> None:
    from docpact.parser.docstring import GoogleParser

    src = tmp_path / "t.py"
    src.write_text(f"def foo(x: int) -> None:\n    {source}    pass\n")
    fns = extract_functions(src)
    fn = fns[0]
    assert fn.docstring_raw is not None
    doc = GoogleParser().parse(fn.docstring_raw)
    _, rule_fn = all_rules()["DOC052"]
    cfg = RuleConfig(
        severity=Severity.ERROR,
        options={"tier": 3, "require_examples_min_tier": 3},
    )
    results = rule_fn(fn, doc, cfg)
    assert len(results) == 1
    modified, conflicts = apply_fixes(results)
    assert not conflicts
    assert modified
    patched = src.read_text(encoding="utf-8")
    assert "Examples:" in patched
    assert "[FILL]" in patched
    assert '"""' in patched


# ---------------------------------------------------------------------------
# Config parsing: require_examples_min_tier round-trips via pyproject.toml
# ---------------------------------------------------------------------------


def test_config_parses_require_examples_min_tier(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.docpact]\nrequire_examples_min_tier = 3\n")
    from docpact.config import load_config

    result = load_config(tmp_path)
    assert result.config.require_examples_min_tier == 3


def test_config_default_is_none(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    from docpact.config import load_config

    result = load_config(tmp_path)
    assert result.config.require_examples_min_tier is None


def test_config_rejects_invalid_value(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.docpact]\nrequire_examples_min_tier = 5\n")
    from docpact.config import ConfigError, load_config

    with pytest.raises(ConfigError, match="require_examples_min_tier"):
        load_config(tmp_path)


# ---------------------------------------------------------------------------
# CLI integration: rule fires end-to-end when config sets min_tier
# ---------------------------------------------------------------------------


def test_cli_fires_when_configured(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from docpact.cli import main

    src = tmp_path / "t.py"
    cfg = tmp_path / "pyproject.toml"
    src.write_text('def foo() -> None:\n    """Summary."""\n')
    cfg.write_text('[tool.docpact]\nselect = ["DOC052"]\nrequire_examples_min_tier = 1\n')
    runner = CliRunner()
    result = runner.invoke(main, ["check", "--config", str(cfg), str(src)], catch_exceptions=False)
    assert "DOC052" in result.output


def test_cli_silent_when_not_configured(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from docpact.cli import main

    src = tmp_path / "t.py"
    cfg = tmp_path / "pyproject.toml"
    src.write_text('def foo() -> None:\n    """Summary."""\n')
    cfg.write_text('[tool.docpact]\nselect = ["DOC052"]\n')
    runner = CliRunner()
    result = runner.invoke(main, ["check", "--config", str(cfg), str(src)], catch_exceptions=False)
    assert "DOC052" not in result.output

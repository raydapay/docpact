"""Tests for NumpyParser — NumPy-style docstring parsing."""

from __future__ import annotations

from docpact.parser.docstring import NumpyParser

_p = NumpyParser()


# ---------------------------------------------------------------------------
# Summary and description
# ---------------------------------------------------------------------------


def test_summary_only() -> None:
    raw = "Return the mean of x."
    result = _p.parse(raw)
    assert result.summary == "Return the mean of x."
    assert result.description is None
    assert result.sections == {}


def test_summary_and_description() -> None:
    raw = "Return the mean of x.\n\nComputed over the first axis."
    result = _p.parse(raw)
    assert result.summary == "Return the mean of x."
    assert result.description == "Computed over the first axis."


# ---------------------------------------------------------------------------
# Parameters section → Args
# ---------------------------------------------------------------------------


def test_parameters_section() -> None:
    raw = (
        "Compute something.\n\n"
        "Parameters\n"
        "----------\n"
        "x : int\n"
        "    The input value.\n"
        "y : str\n"
        "    A label.\n"
    )
    result = _p.parse(raw)
    assert "Args" in result.sections
    args = result.sections["Args"]
    assert args.entries is not None
    keys = [e.key for e in args.entries]
    assert keys == ["x", "y"]
    assert args.entries[0].description == "The input value."


def test_parameters_section_no_type_annotation() -> None:
    raw = "Compute.\n\nParameters\n----------\nx\n    Value.\n"
    result = _p.parse(raw)
    assert "Args" in result.sections
    assert result.sections["Args"].entries[0].key == "x"  # type: ignore[index]


# ---------------------------------------------------------------------------
# Returns section
# ---------------------------------------------------------------------------


def test_returns_section() -> None:
    raw = "Compute.\n\nReturns\n-------\ndict\n    The result mapping.\n"
    result = _p.parse(raw)
    assert "Returns" in result.sections
    assert "result mapping" in (result.sections["Returns"].body or "")


# ---------------------------------------------------------------------------
# Raises section
# ---------------------------------------------------------------------------


def test_raises_section() -> None:
    raw = "Compute.\n\nRaises\n------\nValueError\n    When x is negative.\n"
    result = _p.parse(raw)
    assert "Raises" in result.sections
    entries = result.sections["Raises"].entries
    assert entries is not None
    assert entries[0].description == "When x is negative."


# ---------------------------------------------------------------------------
# Notes / Examples / See Also
# ---------------------------------------------------------------------------


def test_notes_section() -> None:
    raw = "Summary.\n\nNotes\n-----\nThis is important.\n"
    result = _p.parse(raw)
    assert "Notes" in result.sections
    assert "important" in (result.sections["Notes"].body or "")


def test_examples_section() -> None:
    raw = "Summary.\n\nExamples\n--------\n>>> x = 1\n>>> x + 1\n2\n"
    result = _p.parse(raw)
    assert "Examples" in result.sections
    assert "x = 1" in (result.sections["Examples"].body or "")


# ---------------------------------------------------------------------------
# Inline Stability field (same as Google)
# ---------------------------------------------------------------------------


def test_stability_inline_field() -> None:
    raw = "Summary.\n\nStability: beta\n"
    result = _p.parse(raw)
    assert "Stability" in result.sections
    assert result.sections["Stability"].body == "beta"


# ---------------------------------------------------------------------------
# format_name
# ---------------------------------------------------------------------------


def test_format_name() -> None:
    assert _p.format_name() == "numpy"


# ---------------------------------------------------------------------------
# Raw preserved
# ---------------------------------------------------------------------------


def test_raw_preserved() -> None:
    raw = "Summary.\n\nParameters\n----------\nx : int\n    Value.\n"
    result = _p.parse(raw)
    assert result.raw == raw


# ---------------------------------------------------------------------------
# Integration: config format="numpy" selects NumpyParser
# ---------------------------------------------------------------------------


def test_config_numpy_selects_numpy_parser() -> None:
    from docpact.config import Config

    cfg = Config(docstring_format="numpy")
    assert cfg.docstring_format == "numpy"


def test_config_rejects_invalid_format() -> None:
    import pytest

    from docpact.config import ConfigError, _parse_section

    with pytest.raises(ConfigError, match="format"):
        _parse_section({"format": "sphinx"})

"""Tests for generate, show-schema, and list-rules commands."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from click.testing import CliRunner

from docpact.cli import main

if TYPE_CHECKING:
    from pathlib import Path


def _runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


def test_generate_inserts_stub(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")
    r = _runner()
    with r.isolated_filesystem() as td:
        from pathlib import Path as P

        (P(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = r.invoke(main, ["generate", str(src)], catch_exceptions=False)
    assert result.exit_code == 0
    assert '"""' in src.read_text()
    assert "[FILL" in src.read_text()


def test_generate_skips_already_documented(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text('def foo(x: int) -> None:\n    """Already documented."""\n    pass\n')
    r = _runner()
    with r.isolated_filesystem() as td:
        from pathlib import Path as P

        (P(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = r.invoke(main, ["generate", str(src)], catch_exceptions=False)
    assert result.exit_code == 0
    assert "No undocumented functions found." in result.output


def test_generate_reports_count(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n\ndef bar() -> None:\n    pass\n")
    r = _runner()
    with r.isolated_filesystem() as td:
        from pathlib import Path as P

        (P(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = r.invoke(main, ["generate", str(src)], catch_exceptions=False)
    assert result.exit_code == 0
    assert "Generated 2 stub docstring(s)." in result.output


def test_generate_diff_does_not_write(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    original = "def foo(x: int) -> None:\n    pass\n"
    src.write_text(original)
    r = _runner()
    with r.isolated_filesystem() as td:
        from pathlib import Path as P

        (P(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = r.invoke(main, ["generate", "--diff", str(src)], catch_exceptions=False)
    assert result.exit_code == 0
    assert "---" in result.output  # unified diff
    assert src.read_text() == original  # not modified


def test_generate_diff_empty_when_no_stubs_needed(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text('def foo() -> None:\n    """Documented."""\n    pass\n')
    r = _runner()
    with r.isolated_filesystem() as td:
        from pathlib import Path as P

        (P(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = r.invoke(main, ["generate", "--diff", str(src)], catch_exceptions=False)
    assert result.exit_code == 0
    assert result.output == ""


def test_generate_nodo_suppressed_function_skipped(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:  # nodo: DOC001\n    pass\n")
    r = _runner()
    with r.isolated_filesystem() as td:
        from pathlib import Path as P

        (P(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = r.invoke(main, ["generate", str(src)], catch_exceptions=False)
    assert result.exit_code == 0
    assert "No undocumented functions found." in result.output
    assert '"""' not in src.read_text()


# ---------------------------------------------------------------------------
# show-schema
# ---------------------------------------------------------------------------


def test_show_schema_tier1(tmp_path: Path) -> None:
    result = _runner().invoke(main, ["show-schema", "--tier", "1"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "Tier 1" in result.output
    assert "Summary" in result.output


def test_show_schema_tier2(tmp_path: Path) -> None:
    result = _runner().invoke(main, ["show-schema", "--tier", "2"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "Tier 2" in result.output
    assert "Args" in result.output
    assert "Returns" in result.output
    assert "Required" in result.output
    assert "Recommended" in result.output
    assert "Optional" in result.output


def test_show_schema_tier3(tmp_path: Path) -> None:
    result = _runner().invoke(main, ["show-schema", "--tier", "3"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "Tier 3" in result.output
    assert "MCP" in result.output
    assert "Raises" in result.output
    assert "Constraints" in result.output
    assert "Stability" in result.output


def test_show_schema_tier4(tmp_path: Path) -> None:
    result = _runner().invoke(main, ["show-schema", "--tier", "4"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "Tier 4" in result.output
    assert "FastAPI" in result.output


def test_show_schema_invalid_tier_exits_nonzero() -> None:
    result = _runner().invoke(main, ["show-schema", "--tier", "5"])
    assert result.exit_code != 0


def test_show_schema_tier_required() -> None:
    result = _runner().invoke(main, ["show-schema"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# list-rules
# ---------------------------------------------------------------------------


def test_list_rules_text_contains_all_codes() -> None:
    result = _runner().invoke(main, ["list-rules"], catch_exceptions=False)
    assert result.exit_code == 0
    for code in (
        "DOC001",
        "DOC007",
        "DOC012",
        "DOC013",
        "DOC014",
        "DOC051",
        "DOC099",
        "FIX001",
        "MCP001",
    ):
        assert code in result.output


def test_list_rules_text_contains_severity() -> None:
    result = _runner().invoke(main, ["list-rules"], catch_exceptions=False)
    assert "error" in result.output
    assert "warning" in result.output


def test_list_rules_text_shows_fix_markers() -> None:
    result = _runner().invoke(main, ["list-rules"], catch_exceptions=False)
    assert "[*]" in result.output  # at least one fixable rule


def test_list_rules_json_is_valid() -> None:
    result = _runner().invoke(main, ["list-rules", "--format", "json"], catch_exceptions=False)
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) > 0


def test_list_rules_json_doc001_fields() -> None:
    result = _runner().invoke(main, ["list-rules", "--format", "json"], catch_exceptions=False)
    data = json.loads(result.output)
    doc001 = next(r for r in data if r["code"] == "DOC001")
    assert doc001["namespace"] == "DOC"
    assert doc001["severity"] == "error"
    assert doc001["fixable"] is True
    assert doc001["unsafe_fixable"] is False
    assert isinstance(doc001["summary"], str)


def test_list_rules_json_contains_all_rules() -> None:
    from docpact.rules._registry import all_rules

    result = _runner().invoke(main, ["list-rules", "--format", "json"], catch_exceptions=False)
    data = json.loads(result.output)
    codes_in_output = {r["code"] for r in data}
    for code in all_rules():
        assert code in codes_in_output


def test_list_rules_json_sorted_by_code() -> None:
    result = _runner().invoke(main, ["list-rules", "--format", "json"], catch_exceptions=False)
    data = json.loads(result.output)
    codes = [r["code"] for r in data]
    assert codes == sorted(codes)

"""Tests for format_sarif — SARIF 2.1.0 output."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from docpact.cli import main  # registers all rule modules as a side-effect
from docpact.model.diagnostic import RuleResult, Severity, SourceLocation
from docpact.output import format_sarif


def _loc(path: Path, line: int = 1, col: int = 0) -> SourceLocation:
    return SourceLocation(file_path=path, line=line, column=col)


def _result(
    path: Path,
    code: str = "DOC001",
    line: int = 1,
    col: int = 0,
    severity: Severity = Severity.ERROR,
    message: str | None = None,
) -> RuleResult:
    return RuleResult(
        code=code,
        severity=severity,
        message=message or f"{code} message",
        location=_loc(path, line, col),
    )


# ---------------------------------------------------------------------------
# Top-level document shape
# ---------------------------------------------------------------------------


def test_sarif_is_valid_json(tmp_path: Path) -> None:
    output = format_sarif([_result(tmp_path / "foo.py")])
    doc = json.loads(output)
    assert isinstance(doc, dict)


def test_sarif_version(tmp_path: Path) -> None:
    doc = json.loads(format_sarif([_result(tmp_path / "foo.py")]))
    assert doc["version"] == "2.1.0"


def test_sarif_schema_key(tmp_path: Path) -> None:
    doc = json.loads(format_sarif([_result(tmp_path / "foo.py")]))
    assert "$schema" in doc
    assert "sarif" in doc["$schema"].lower()


def test_sarif_has_runs(tmp_path: Path) -> None:
    doc = json.loads(format_sarif([]))
    assert "runs" in doc
    assert len(doc["runs"]) == 1


# ---------------------------------------------------------------------------
# Tool driver
# ---------------------------------------------------------------------------


def test_sarif_tool_driver_name(tmp_path: Path) -> None:
    doc = json.loads(format_sarif([]))
    assert doc["runs"][0]["tool"]["driver"]["name"] == "docpact"


def test_sarif_tool_driver_version_present(tmp_path: Path) -> None:
    doc = json.loads(format_sarif([]))
    assert "version" in doc["runs"][0]["tool"]["driver"]


def test_sarif_driver_rules_populated(tmp_path: Path) -> None:
    doc = json.loads(format_sarif([]))
    rules = doc["runs"][0]["tool"]["driver"]["rules"]
    assert len(rules) > 0
    ids = {r["id"] for r in rules}
    assert "DOC001" in ids


def test_sarif_driver_rule_shape(tmp_path: Path) -> None:
    doc = json.loads(format_sarif([]))
    rule = next(r for r in doc["runs"][0]["tool"]["driver"]["rules"] if r["id"] == "DOC001")
    assert "shortDescription" in rule
    assert "text" in rule["shortDescription"]
    assert "defaultConfiguration" in rule
    assert rule["defaultConfiguration"]["level"] in {"error", "warning", "note"}


# ---------------------------------------------------------------------------
# Results shape
# ---------------------------------------------------------------------------


def test_sarif_empty_results(tmp_path: Path) -> None:
    doc = json.loads(format_sarif([]))
    assert doc["runs"][0]["results"] == []


def test_sarif_result_rule_id(tmp_path: Path) -> None:
    doc = json.loads(format_sarif([_result(tmp_path / "f.py", code="DOC007")]))
    assert doc["runs"][0]["results"][0]["ruleId"] == "DOC007"


def test_sarif_result_message(tmp_path: Path) -> None:
    f = tmp_path / "f.py"
    doc = json.loads(format_sarif([_result(f, message="param x undocumented")]))
    assert doc["runs"][0]["results"][0]["message"]["text"] == "param x undocumented"


def test_sarif_result_level_error(tmp_path: Path) -> None:
    doc = json.loads(format_sarif([_result(tmp_path / "f.py", severity=Severity.ERROR)]))
    assert doc["runs"][0]["results"][0]["level"] == "error"


def test_sarif_result_level_warning(tmp_path: Path) -> None:
    doc = json.loads(format_sarif([_result(tmp_path / "f.py", severity=Severity.WARNING)]))
    assert doc["runs"][0]["results"][0]["level"] == "warning"


def test_sarif_result_level_off_maps_to_note(tmp_path: Path) -> None:
    doc = json.loads(format_sarif([_result(tmp_path / "f.py", severity=Severity.OFF)]))
    assert doc["runs"][0]["results"][0]["level"] == "note"


def test_sarif_result_location_present(tmp_path: Path) -> None:
    doc = json.loads(format_sarif([_result(tmp_path / "f.py")]))
    result = doc["runs"][0]["results"][0]
    assert "locations" in result
    assert len(result["locations"]) == 1


def test_sarif_result_start_line(tmp_path: Path) -> None:
    f = tmp_path / "f.py"
    doc = json.loads(format_sarif([_result(f, line=42)]))
    region = doc["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]
    assert region["startLine"] == 42


def test_sarif_result_start_column_one_based(tmp_path: Path) -> None:
    f = tmp_path / "f.py"
    # col=0 in the model → startColumn=1 in SARIF (1-based)
    doc = json.loads(format_sarif([_result(f, col=0)]))
    region = doc["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]
    assert region["startColumn"] == 1


def test_sarif_result_start_column_nonzero(tmp_path: Path) -> None:
    f = tmp_path / "f.py"
    doc = json.loads(format_sarif([_result(f, col=4)]))
    region = doc["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]
    assert region["startColumn"] == 5


# ---------------------------------------------------------------------------
# URI handling
# ---------------------------------------------------------------------------


def test_sarif_absolute_uri_when_no_cwd(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    doc = json.loads(format_sarif([_result(f)]))
    artifact = doc["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]
    assert artifact["uri"].startswith("file://")
    assert "foo.py" in artifact["uri"]


def test_sarif_relative_uri_when_cwd_provided(tmp_path: Path) -> None:
    sub = tmp_path / "pkg"
    sub.mkdir()
    f = sub / "foo.py"
    doc = json.loads(format_sarif([_result(f)], cwd=tmp_path))
    artifact = doc["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]
    assert artifact["uri"] == "pkg/foo.py"
    assert artifact.get("uriBaseId") == "%SRCROOT%"


def test_sarif_original_uri_base_ids_set_when_cwd_provided(tmp_path: Path) -> None:
    f = tmp_path / "f.py"
    doc = json.loads(format_sarif([_result(f)], cwd=tmp_path))
    run = doc["runs"][0]
    assert "%SRCROOT%" in run.get("originalUriBaseIds", {})


def test_sarif_no_original_uri_base_ids_when_no_cwd(tmp_path: Path) -> None:
    f = tmp_path / "f.py"
    doc = json.loads(format_sarif([_result(f)]))
    run = doc["runs"][0]
    assert "originalUriBaseIds" not in run


def test_sarif_path_outside_cwd_falls_back_to_absolute(tmp_path: Path) -> None:
    outside = tmp_path.parent / "other.py"
    inner = tmp_path / "sub"
    inner.mkdir()
    doc = json.loads(format_sarif([_result(outside)], cwd=inner))
    artifact = doc["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]
    assert artifact["uri"].startswith("file://")


# ---------------------------------------------------------------------------
# Multiple results
# ---------------------------------------------------------------------------


def test_sarif_multiple_results(tmp_path: Path) -> None:
    f = tmp_path / "foo.py"
    results = [
        _result(f, code="DOC001", line=1),
        _result(f, code="DOC007", line=10),
    ]
    doc = json.loads(format_sarif(results))
    sarif_results = doc["runs"][0]["results"]
    assert len(sarif_results) == 2
    rule_ids = {r["ruleId"] for r in sarif_results}
    assert rule_ids == {"DOC001", "DOC007"}


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_sarif_format(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text("def foo(x: int) -> None:\n    pass\n")

    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(
            main,
            ["check", "--format", "sarif", "--exit-zero", str(src)],
            catch_exceptions=False,
        )

    assert result.exit_code == 0
    doc = json.loads(result.output)
    assert doc["version"] == "2.1.0"
    rule_ids = {r["ruleId"] for r in doc["runs"][0]["results"]}
    assert "DOC001" in rule_ids


def test_cli_sarif_empty_when_no_violations(tmp_path: Path) -> None:
    src = tmp_path / "t.py"
    src.write_text('"""Module docstring."""\n\n\ndef foo() -> None:\n    """Do foo."""\n    pass\n')

    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        (Path(td) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = runner.invoke(
            main,
            ["check", "--format", "sarif", "--exit-zero", str(src)],
            catch_exceptions=False,
        )

    assert result.exit_code == 0
    doc = json.loads(result.output)
    assert doc["runs"][0]["results"] == []

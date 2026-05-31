"""Tests for the LSP client layer (cross-file resolution; ADR-009).

No real language server: the lifecycle (spawn → initialize → didOpen →
definition → shutdown) is driven against a fake server subprocess
(``tests/fixtures/fake_lsp_server.py``) — pure Python, offline, deterministic,
per the ADR-009 invariant. Wire-shape normalization is unit-tested directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from docpact.config import ConfigError, LspConfig, load_config
from docpact.lsp import LSPClient, LSPError, LspLocation
from docpact.lsp.client import _normalize_locations

_FAKE = Path(__file__).parent / "fixtures" / "fake_lsp_server.py"


def _client(
    mode: str, root: Path, *, timeout: float = 5.0, log_file: Path | None = None
) -> LSPClient:
    """Build an LSPClient wired to the fake server in the given mode."""
    return LSPClient((sys.executable, str(_FAKE), mode), root, timeout=timeout, log_file=log_file)


# --- config -------------------------------------------------------------------


def test_lsp_defaults_when_absent(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.docpact]\nselect = ["DOC"]\n')
    lsp = load_config(tmp_path).config.lsp
    assert lsp.server == ("ty", "server")
    assert lsp.timeout == 15.0


def test_lsp_full_parse(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.docpact.lsp]\nserver = ["pyright-langserver", "--stdio"]\ntimeout = 30\n'
        'log = "lsp.log"\n'
    )
    lsp = load_config(tmp_path).config.lsp
    assert lsp.server == ("pyright-langserver", "--stdio")
    assert lsp.timeout == 30.0
    assert lsp.log == "lsp.log"


def test_lsp_log_defaults_to_none(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.docpact]\nselect = ["DOC"]\n')
    assert load_config(tmp_path).config.lsp.log is None


def test_lsp_log_must_be_string(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.docpact.lsp]\nlog = 5\n")
    with pytest.raises(ConfigError, match=r"lsp\.log"):
        load_config(tmp_path)


def test_lsp_log_captures_server_stderr(tmp_path: Path) -> None:
    # With a log path, the server's stderr is appended there rather than discarded.
    log = tmp_path / "lsp.log"
    with _client("stderr-noise", tmp_path, log_file=log) as client:
        client.did_open(_FAKE)  # any didOpen; the noise is written at startup
    assert log.exists()
    assert "Confusing indentation" in log.read_text(encoding="utf-8")


def test_lsp_log_unwritable_path_falls_back_to_discard(tmp_path: Path) -> None:
    # A log path that cannot be opened must not fail the run.
    bad = tmp_path / "missing-dir" / "lsp.log"  # parent does not exist
    with _client("location", tmp_path, log_file=bad) as client:
        loc = client.definition(_FAKE, 0, 0)
    assert loc  # the run proceeds normally
    assert not bad.exists()


def test_lsp_empty_server_rejected(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.docpact.lsp]\nserver = []\n")
    with pytest.raises(Exception, match=r"lsp\.server"):
        load_config(tmp_path)


def test_lsp_timeout_must_be_positive(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.docpact.lsp]\ntimeout = 0\n")
    with pytest.raises(Exception, match=r"lsp\.timeout"):
        load_config(tmp_path)


def test_lsp_timeout_rejects_bool(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.docpact.lsp]\ntimeout = true\n")
    with pytest.raises(Exception, match=r"lsp\.timeout"):
        load_config(tmp_path)


def test_lsp_not_a_table(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.docpact]\nlsp = "nope"\n')
    with pytest.raises(Exception, match="lsp: expected a table"):
        load_config(tmp_path)


# --- normalization (pure, no subprocess) --------------------------------------


def test_normalize_none_is_empty() -> None:
    assert _normalize_locations(None) == []


def test_normalize_single_location() -> None:
    result = {
        "uri": "file:///a.py",
        "range": {"start": {"line": 2, "character": 3}, "end": {"line": 2, "character": 9}},
    }
    assert _normalize_locations(result) == [LspLocation("file:///a.py", 2, 3, 2, 9)]


def test_normalize_list_of_locations() -> None:
    result = [
        {
            "uri": "file:///a.py",
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
        },
        {
            "uri": "file:///b.py",
            "range": {"start": {"line": 1, "character": 1}, "end": {"line": 1, "character": 2}},
        },
    ]
    locs = _normalize_locations(result)
    assert [loc.uri for loc in locs] == ["file:///a.py", "file:///b.py"]


def test_normalize_locationlink_prefers_target_selection_range() -> None:
    result = {
        "targetUri": "file:///a.py",
        "targetRange": {"start": {"line": 5, "character": 0}, "end": {"line": 9, "character": 0}},
        "targetSelectionRange": {
            "start": {"line": 5, "character": 6},
            "end": {"line": 5, "character": 20},
        },
    }
    assert _normalize_locations(result) == [LspLocation("file:///a.py", 5, 6, 5, 20)]


def test_normalize_locationlink_falls_back_to_target_range() -> None:
    result = {
        "targetUri": "file:///a.py",
        "targetRange": {"start": {"line": 5, "character": 0}, "end": {"line": 9, "character": 4}},
    }
    assert _normalize_locations(result) == [LspLocation("file:///a.py", 5, 0, 9, 4)]


def test_normalize_drops_items_without_uri() -> None:
    assert _normalize_locations([{"range": {}}, "garbage", 42]) == []


def test_normalize_tolerates_missing_range() -> None:
    assert _normalize_locations({"uri": "file:///a.py"}) == [
        LspLocation("file:///a.py", 0, 0, 0, 0)
    ]


# --- lifecycle against the fake server ----------------------------------------


def test_definition_resolves_location(tmp_path: Path) -> None:
    query = tmp_path / "tools.py"
    query.write_text("x = 1\n")
    with _client("location", tmp_path) as client:
        client.did_open(query)
        locs = client.definition(query, 0, 0)
    assert len(locs) == 1
    assert locs[0].uri.endswith("schemas.py")
    assert (locs[0].start_line, locs[0].start_char) == (5, 6)


def test_definition_resolves_location_list(tmp_path: Path) -> None:
    query = tmp_path / "tools.py"
    query.write_text("x = 1\n")
    with _client("location-list", tmp_path) as client:
        locs = client.definition(query, 0, 0)
    assert len(locs) == 1 and locs[0].uri.endswith("schemas.py")


def test_definition_resolves_locationlink(tmp_path: Path) -> None:
    query = tmp_path / "tools.py"
    query.write_text("x = 1\n")
    with _client("locationlink", tmp_path) as client:
        locs = client.definition(query, 0, 0)
    assert locs == [LspLocation("file:///workspace/schemas.py", 5, 6, 5, 30)]


def test_definition_empty_after_readiness_budget(tmp_path: Path) -> None:
    query = tmp_path / "tools.py"
    query.write_text("x = 1\n")
    # Always-empty server: readiness retry exhausts the (short) budget, then []
    # is returned — an unresolved symbol, not an error.
    with _client("empty", tmp_path, timeout=0.3) as client:
        locs = client.definition(query, 0, 0)
    assert locs == []


def test_definition_retries_until_resolved(tmp_path: Path) -> None:
    query = tmp_path / "tools.py"
    query.write_text("x = 1\n")
    # First call empty (server still "indexing"), second resolves.
    with _client("delayed", tmp_path, timeout=2.0) as client:
        locs = client.definition(query, 0, 0)
    assert len(locs) == 1 and locs[0].uri.endswith("schemas.py")


def test_definition_server_error_raises(tmp_path: Path) -> None:
    query = tmp_path / "tools.py"
    query.write_text("x = 1\n")
    with _client("error", tmp_path) as client, pytest.raises(LSPError, match="returned an error"):
        client.definition(query, 0, 0)


def test_definition_timeout_raises(tmp_path: Path) -> None:
    query = tmp_path / "tools.py"
    query.write_text("x = 1\n")
    with (
        _client("hang", tmp_path, timeout=0.3) as client,
        pytest.raises(LSPError, match="did not respond"),
    ):
        client.definition(query, 0, 0)


def test_initialize_error_raises(tmp_path: Path) -> None:
    with pytest.raises(LSPError, match="returned an error"), _client("initialize-error", tmp_path):
        pass


def test_missing_server_raises(tmp_path: Path) -> None:
    client = LSPClient(("docpact-no-such-server-binary-xyz",), tmp_path, timeout=1.0)
    with pytest.raises(LSPError, match="could not start LSP server"), client:
        pass


def test_empty_server_command_rejected(tmp_path: Path) -> None:
    with pytest.raises(LSPError, match="server command is empty"):
        LSPClient((), tmp_path)


def test_did_open_missing_file_raises(tmp_path: Path) -> None:
    with _client("location", tmp_path) as client, pytest.raises(LSPError, match="could not read"):
        client.did_open(tmp_path / "does_not_exist.py")


def test_lsp_config_default_dataclass() -> None:
    assert LspConfig().server == ("ty", "server")
    assert LspConfig().timeout == 15.0

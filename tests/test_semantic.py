"""Tests for the semantic layer (SEM): config, backend, analyzer, CLI command.

No network: the OpenAI-compat backend is tested by monkeypatching urlopen, and
the analyzer/CLI by a FakeBackend. The LLM is never actually called.
"""

from __future__ import annotations

import io
import json
import subprocess
import urllib.error
from pathlib import Path

import pytest
from click.testing import CliRunner

from docpact.cli import main
from docpact.config import SemanticConfig, load_config
from docpact.model.function_info import FunctionInfo, ParameterInfo
from docpact.model.module_info import ModuleInfo
from docpact.semantic import analyzer, backend

# --- helpers ------------------------------------------------------------------


def _fn(name: str, *, doc: str | None = "Summary.", line: int = 1) -> FunctionInfo:
    """Build a minimal module-level FunctionInfo with one parameter."""
    return FunctionInfo(
        name=name,
        file_path=Path("m.py"),
        line=line,
        column=0,
        parameters=(ParameterInfo(name="x", annotation="int", default=None, kind="positional"),),
        return_annotation="str",
        decorators=(),
        docstring_raw=doc,
        docstring_line=line,
        containing_class=None,
        def_start_offset=0,
        def_end_offset=0,
        docstring_start_offset=None,
        docstring_end_offset=None,
    )


class _FakeBackend:
    """An LLMBackend that returns a canned reply and records calls."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.reply


# --- config -------------------------------------------------------------------


def test_semantic_defaults_when_absent(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.docpact]\nselect = ["DOC"]\n')
    sem = load_config(tmp_path).config.semantic
    assert sem.backend == "openai-compat"
    assert sem.model == ""
    assert sem.api_base is None
    assert sem.api_key_env == "OPENAI_API_KEY"
    assert sem.min_tier == 3


def test_semantic_full_parse(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.docpact.semantic]\n"
        'backend = "openai-compat"\n'
        'model = "openai/gpt-4o-mini"\n'
        'api_base = "https://models.github.ai/inference"\n'
        'api_key_env = "GITHUB_TOKEN"\n'
        "min_tier = 2\n"
    )
    sem = load_config(tmp_path).config.semantic
    assert sem.model == "openai/gpt-4o-mini"
    assert sem.api_base == "https://models.github.ai/inference"
    assert sem.api_key_env == "GITHUB_TOKEN"
    assert sem.min_tier == 2


def test_semantic_min_tier_validated(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.docpact.semantic]\nmin_tier = 9\n")
    with pytest.raises(Exception, match="min_tier"):
        load_config(tmp_path)


def test_semantic_finding_threshold_defaults_to_weak(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.docpact]\nselect = ["DOC"]\n')
    assert load_config(tmp_path).config.semantic.finding_threshold == "weak"


def test_semantic_finding_threshold_parsed(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.docpact.semantic]\nfinding_threshold = "empty"\n'
    )
    assert load_config(tmp_path).config.semantic.finding_threshold == "empty"


def test_semantic_finding_threshold_validated(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.docpact.semantic]\nfinding_threshold = "loud"\n'
    )
    with pytest.raises(Exception, match="finding_threshold"):
        load_config(tmp_path)


def test_semantic_max_retries_defaults(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.docpact]\nselect = ["DOC"]\n')
    assert load_config(tmp_path).config.semantic.max_retries == 2


def test_semantic_max_retries_parsed(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.docpact.semantic]\nmax_retries = 5\n")
    assert load_config(tmp_path).config.semantic.max_retries == 5


def test_semantic_max_retries_validated(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.docpact.semantic]\nmax_retries = 99\n")
    with pytest.raises(Exception, match="max_retries"):
        load_config(tmp_path)


def test_semantic_scan_modes_default_function(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.docpact]\nselect = ["DOC"]\n')
    assert load_config(tmp_path).config.semantic.scan_modes == ("function",)


def test_semantic_scan_modes_parsed(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.docpact.semantic]\nscan_modes = ["function", "module"]\n'
    )
    assert load_config(tmp_path).config.semantic.scan_modes == ("function", "module")


def test_semantic_scan_modes_rejects_unknown(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.docpact.semantic]\nscan_modes = ["galaxy"]\n')
    with pytest.raises(Exception, match="scan_modes"):
        load_config(tmp_path)


def test_semantic_scan_modes_rejects_empty(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.docpact.semantic]\nscan_modes = []\n")
    with pytest.raises(Exception, match="scan_modes"):
        load_config(tmp_path)


# --- backend: make_backend factory --------------------------------------------


def test_make_backend_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(backend.SemanticError, match="no API key"):
        backend.make_backend(SemanticConfig(model="m", api_base="https://x/v1"))


def test_make_backend_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    with pytest.raises(backend.SemanticError, match="unknown backend"):
        backend.make_backend(SemanticConfig(backend="gemini", model="m"))


def test_make_backend_requires_api_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    with pytest.raises(backend.SemanticError, match="api_base"):
        backend.make_backend(SemanticConfig(model="m"))


def test_make_backend_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    be = backend.make_backend(SemanticConfig(model="m", api_base="https://x/v1"))
    assert isinstance(be, backend.OpenAICompatBackend)


# --- backend: OpenAICompatBackend HTTP (mocked urlopen) -----------------------


class _Resp:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def test_backend_success(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(req: object, timeout: float) -> _Resp:
        captured["url"] = req.full_url  # type: ignore[attr-defined]
        captured["payload"] = json.loads(req.data)  # type: ignore[attr-defined]
        reply = {"choices": [{"message": {"content": '{"findings":[]}'}}]}
        return _Resp(json.dumps(reply).encode())

    monkeypatch.setattr(backend.urllib.request, "urlopen", fake_urlopen)
    be = backend.OpenAICompatBackend(api_base="https://x/v1/", model="m", api_key="k")
    out = be.complete("sys", "usr")
    assert out == '{"findings":[]}'
    assert str(captured["url"]).endswith("/chat/completions")
    assert captured["payload"]["model"] == "m"  # type: ignore[index]


@pytest.mark.parametrize(
    ("code", "match"),
    [(429, "rate-limited"), (401, "auth failed"), (500, "HTTP 500")],
)
def test_backend_http_errors(monkeypatch: pytest.MonkeyPatch, code: int, match: str) -> None:
    def fake_urlopen(req: object, timeout: float) -> _Resp:
        raise urllib.error.HTTPError("u", code, "err", {}, io.BytesIO(b"detail"))  # type: ignore[arg-type]

    monkeypatch.setattr(backend.urllib.request, "urlopen", fake_urlopen)
    # max_retries=0: this test pins error *classification*, not retry behaviour.
    be = backend.OpenAICompatBackend(api_base="https://x/v1", model="m", api_key="k", max_retries=0)
    with pytest.raises(backend.SemanticError, match=match):
        be.complete("s", "u")


def test_backend_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """A transient 503 then 200 succeeds within max_retries; backoff sleeps recorded."""
    calls = {"n": 0}

    def fake_urlopen(req: object, timeout: float) -> _Resp:
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError("u", 503, "busy", {}, io.BytesIO(b"high demand"))  # type: ignore[arg-type]
        return _Resp(json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode())

    monkeypatch.setattr(backend.urllib.request, "urlopen", fake_urlopen)
    slept: list[float] = []
    be = backend.OpenAICompatBackend(
        api_base="https://x/v1", model="m", api_key="k", max_retries=2, sleep=slept.append
    )
    assert be.complete("s", "u") == "{}"
    assert calls["n"] == 2
    assert slept == [1.0]  # one backoff before the successful retry


def test_backend_retries_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Persistent 429 exhausts max_retries and raises, reporting the attempt count."""
    calls = {"n": 0}

    def fake_urlopen(req: object, timeout: float) -> _Resp:
        calls["n"] += 1
        raise urllib.error.HTTPError("u", 429, "rl", {}, io.BytesIO(b"quota"))  # type: ignore[arg-type]

    monkeypatch.setattr(backend.urllib.request, "urlopen", fake_urlopen)
    slept: list[float] = []
    be = backend.OpenAICompatBackend(
        api_base="https://x/v1", model="m", api_key="k", max_retries=2, sleep=slept.append
    )
    with pytest.raises(backend.SemanticError, match=r"rate-limited.*after 3 attempt"):
        be.complete("s", "u")
    assert calls["n"] == 3  # initial + 2 retries
    assert slept == [1.0, 2.0]  # capped exponential backoff


def test_backend_auth_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """401 is a permanent auth failure — never retried even with retries enabled."""
    calls = {"n": 0}

    def fake_urlopen(req: object, timeout: float) -> _Resp:
        calls["n"] += 1
        raise urllib.error.HTTPError("u", 401, "no", {}, io.BytesIO(b"bad key"))  # type: ignore[arg-type]

    monkeypatch.setattr(backend.urllib.request, "urlopen", fake_urlopen)
    be = backend.OpenAICompatBackend(api_base="https://x/v1", model="m", api_key="k", max_retries=3)
    with pytest.raises(backend.SemanticError, match="auth failed"):
        be.complete("s", "u")
    assert calls["n"] == 1  # no retry


def test_backend_bad_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req: object, timeout: float) -> _Resp:
        return _Resp(json.dumps({"nope": True}).encode())

    monkeypatch.setattr(backend.urllib.request, "urlopen", fake_urlopen)
    be = backend.OpenAICompatBackend(api_base="https://x/v1", model="m", api_key="k")
    with pytest.raises(backend.SemanticError, match="unexpected response shape"):
        be.complete("s", "u")


# --- analyzer -----------------------------------------------------------------


def test_analyze_maps_verdicts() -> None:
    funcs = [_fn("f_empty", line=10), _fn("f_good", line=20), _fn("f_weak", line=30)]
    reply = json.dumps(
        {
            "findings": [
                {"name": "f_empty", "verdict": "empty", "issues": ["says nothing"]},
                {"name": "f_good", "verdict": "good", "issues": []},
                {
                    "name": "f_weak",
                    "verdict": "weak",
                    "issues": ["missing precondition", "side effect"],
                },
            ]
        }
    )
    report = analyzer.analyze(funcs, _FakeBackend(reply))
    assert report.units_reviewed == 3
    assert report.requests == 1
    codes = [(r.code, r.location.line) for r in report.results]
    assert codes == [("SEM001", 10), ("SEM001", 30)]  # good skipped, sorted by line
    assert "missing precondition; side effect" in report.results[1].message


def _verdicts_reply() -> str:
    """A reply with one each of empty / good / weak, for threshold tests."""
    return json.dumps(
        {
            "findings": [
                {"name": "f_empty", "verdict": "empty", "issues": ["says nothing"]},
                {"name": "f_good", "verdict": "good", "issues": []},
                {"name": "f_weak", "verdict": "weak", "issues": ["missing precondition"]},
            ]
        }
    )


def test_threshold_weak_surfaces_weak_and_empty() -> None:
    funcs = [_fn("f_empty", line=10), _fn("f_good", line=20), _fn("f_weak", line=30)]
    report = analyzer.analyze(funcs, _FakeBackend(_verdicts_reply()), threshold="weak")
    assert [r.location.line for r in report.results] == [10, 30]  # empty + weak


def test_threshold_empty_drops_weak() -> None:
    funcs = [_fn("f_empty", line=10), _fn("f_good", line=20), _fn("f_weak", line=30)]
    report = analyzer.analyze(funcs, _FakeBackend(_verdicts_reply()), threshold="empty")
    assert [r.location.line for r in report.results] == [10]  # only empty surfaces
    assert all(r.message.startswith("empty:") for r in report.results)


def _mod(label: str, *, doc: str = "Does a thing.", symbols: tuple[str, ...] = ()) -> ModuleInfo:
    """Build a ModuleInfo whose file_path str is `label` (the prompt/reply key)."""
    return ModuleInfo(file_path=Path(label), docstring_raw=doc, symbols=symbols)


def test_analyze_modules_maps_weak_dimensions() -> None:
    mods = [_mod("a.py"), _mod("b.py"), _mod("c.py")]
    reply = json.dumps(
        {
            "findings": [
                {
                    "name": "a.py",
                    "scope": "weak",
                    "scope_evidence": "claims HTTP",
                    "orientation": "good",
                    "orientation_evidence": "",
                },
                {
                    "name": "b.py",
                    "scope": "good",
                    "scope_evidence": "",
                    "orientation": "weak",
                    "orientation_evidence": "boilerplate",
                },
                {
                    "name": "c.py",
                    "scope": "good",
                    "scope_evidence": "",
                    "orientation": "good",
                    "orientation_evidence": "",
                },
            ]
        }
    )
    report = analyzer.analyze_modules(mods, _FakeBackend(reply))
    assert report.units_reviewed == 3
    codes = [(r.code, str(r.location.file_path)) for r in report.results]
    assert codes == [("SEM002", "a.py"), ("SEM002", "b.py")]  # c.py good → no finding
    assert "scope: claims HTTP" in report.results[0].message
    assert "orientation: boilerplate" in report.results[1].message
    assert report.results[0].location.line == 1


def test_analyze_modules_both_dimensions_one_finding() -> None:
    reply = json.dumps(
        {
            "findings": [
                {
                    "name": "m.py",
                    "scope": "weak",
                    "scope_evidence": "wrong domain",
                    "orientation": "weak",
                    "orientation_evidence": "empty",
                }
            ]
        }
    )
    report = analyzer.analyze_modules([_mod("m.py")], _FakeBackend(reply))
    assert len(report.results) == 1
    assert "scope: wrong domain" in report.results[0].message
    assert "orientation: empty" in report.results[0].message


def test_analyze_modules_unknown_label_skipped() -> None:
    reply = json.dumps({"findings": [{"name": "ghost.py", "scope": "weak", "scope_evidence": "x"}]})
    report = analyzer.analyze_modules([_mod("real.py")], _FakeBackend(reply))
    assert report.results == []


def test_analyze_modules_unparseable_skipped() -> None:
    report = analyzer.analyze_modules([_mod("m.py")], _FakeBackend("not json"))
    assert report.results == []
    assert report.requests == 1


def test_prompt_fingerprint_stable_short_and_distinct() -> None:
    fp = analyzer.prompt_fingerprint
    assert fp("abc") == fp("abc")  # deterministic
    assert len(fp("abc")) == 12 and all(c in "0123456789abcdef" for c in fp("abc"))
    assert fp("abc") != fp("abd")  # tracks content
    # The two shipped prompts are distinct, so their fingerprints must differ.
    assert fp(analyzer.SYSTEM) != fp(analyzer.MODULE_SYSTEM)


def test_analyze_unparseable_reply_skipped() -> None:
    report = analyzer.analyze([_fn("f")], _FakeBackend("not json at all"))
    assert report.results == []
    assert report.requests == 1


def test_analyze_tolerates_fenced_json() -> None:
    reply = '```json\n{"findings":[{"name":"f","verdict":"empty","issues":["x"]}]}\n```'
    report = analyzer.analyze([_fn("f")], _FakeBackend(reply))
    assert len(report.results) == 1


@pytest.mark.parametrize(
    "reply",
    [
        '```json\n{"findings":[]}\n```',  # language-tagged fence
        '```\n{"findings":[]}\n```',  # tagless fence
        '```json{"findings":[]}```',  # tag with no newline
        '{"findings":[]}',  # no fence at all
    ],
)
def test_extract_json_fence_variants(reply: str) -> None:
    """The fence/tag strip yields the object, never eats into the JSON body.

    Guards the ``removeprefix("json")`` fix: ``lstrip("json")`` stripped the
    character set, which a tagless ``{...}`` happens to survive but a payload
    leading with j/o/s/n would not. Locks the contract directly on _extract_json.
    """
    assert analyzer._extract_json(reply) == {"findings": []}


def test_analyze_tolerates_bare_list_reply() -> None:
    """A top-level JSON array (no `findings` wrapper) is normalized, not crashed on.

    Gemini emits the findings list as a bare top-level array even in JSON mode,
    where OpenAI-family models wrap it in an object. Regression for the
    AttributeError that aborted the whole run.
    """
    reply = json.dumps([{"name": "f", "verdict": "weak", "issues": ["x"]}])
    report = analyzer.analyze([_fn("f")], _FakeBackend(reply))
    assert len(report.results) == 1
    assert report.results[0].message.startswith("weak:")


def test_analyze_modules_tolerates_bare_list_reply() -> None:
    """SEM002 path also normalizes a bare top-level array reply (Gemini shape)."""
    reply = json.dumps([{"name": "m.py", "scope": "weak", "scope_evidence": "wrong domain"}])
    report = analyzer.analyze_modules([_mod("m.py")], _FakeBackend(reply))
    assert len(report.results) == 1
    assert "scope: wrong domain" in report.results[0].message


def test_analyze_non_dict_json_skipped() -> None:
    """Valid JSON that is neither object nor list yields no findings, no crash."""
    report = analyzer.analyze([_fn("f")], _FakeBackend("42"))
    assert report.results == []
    assert report.requests == 1


def test_analyze_skips_non_dict_findings_items() -> None:
    """A findings array containing non-object items skips them instead of crashing."""
    reply = json.dumps({"findings": ["garbage", {"name": "f", "verdict": "weak", "issues": ["x"]}]})
    report = analyzer.analyze([_fn("f")], _FakeBackend(reply))
    assert len(report.results) == 1


def test_build_batches_splits_on_budget() -> None:
    funcs = [_fn(f"f{i}", doc="x" * 500) for i in range(10)]
    batches = analyzer.build_batches(funcs, batch_chars=1200)
    assert len(batches) > 1
    assert sum(len(b) for b in batches) == 10


def test_user_prompt_lists_all() -> None:
    prompt = analyzer.user_prompt([_fn("alpha"), _fn("beta")])
    assert "alpha" in prompt and "beta" in prompt and "Return JSON only" in prompt


# --- CLI: docpact semantic ----------------------------------------------------

_SRC = '''"""Module."""


def do_thing(x: int) -> str:
    """Do the thing.

    Args:
        x: A number.

    Returns:
        Text.
    """
    return str(x)
'''


def test_semantic_dry_run_no_network() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        Path(td, "m.py").write_text(_SRC)
        result = runner.invoke(main, ["semantic", "m.py", "--min-tier", "2", "--dry-run"])
    assert result.exit_code == 0
    assert "SYSTEM" in result.output
    assert "no API call" in result.output


def test_semantic_no_functions_in_scope() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        Path(td, "m.py").write_text(
            '"""M."""\n\n\ndef _helper(x):\n    """Internal."""\n    return x\n'
        )
        result = runner.invoke(main, ["semantic", "m.py"])  # default min-tier 3; _helper is tier 1
    assert result.exit_code == 0
    assert "Nothing in scope" in result.output


class _ModuleEchoBackend:
    """Backend that flags scope=weak for each module label found in the prompt.

    Reads the `module: <label>` lines from the user prompt so the reply's `name`
    matches whatever path the CLI used — robust to relative/absolute path forms.
    """

    def complete(self, system: str, user: str) -> str:
        labels = [ln[len("module: ") :] for ln in user.splitlines() if ln.startswith("module: ")]
        return json.dumps(
            {
                "findings": [
                    {
                        "name": label,
                        "scope": "weak",
                        "scope_evidence": "claims X",
                        "orientation": "good",
                        "orientation_evidence": "",
                    }
                    for label in labels
                ]
            }
        )


def test_semantic_module_dry_run() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        Path(td, "m.py").write_text(
            '"""A module that does things."""\n\n\ndef pub():\n    """Go."""\n'
        )
        result = runner.invoke(main, ["semantic", "m.py", "--scan-modes", "module", "--dry-run"])
    assert result.exit_code == 0
    assert "SYSTEM (module)" in result.output
    assert "public symbols" in result.output
    assert "no API call" in result.output


def test_semantic_module_run_with_fake_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("docpact.cli.make_backend", lambda cfg: _ModuleEchoBackend())
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        Path(td, "m.py").write_text('"""A module."""\n\n\ndef pub():\n    """Go."""\n')
        result = runner.invoke(
            main, ["semantic", "m.py", "--scan-modes", "module"], catch_exceptions=False
        )
    assert result.exit_code == 1  # advisory finding → non-zero
    assert "SEM002" in result.output
    assert "module(s)" in result.output


def test_semantic_module_scan_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default scan_modes is function-only; a module-only weak signal must not fire.
    monkeypatch.setattr("docpact.cli.make_backend", lambda cfg: _ModuleEchoBackend())
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        # No tier-3 functions, so the function scan finds nothing in scope.
        Path(td, "m.py").write_text('"""A module."""\n\n\ndef _p():\n    """x."""\n')
        result = runner.invoke(main, ["semantic", "m.py"], catch_exceptions=False)
    assert "SEM002" not in result.output


def test_semantic_changed_only_restricts_scope() -> None:
    # --changed-only scopes the scan to .py files changed vs a git ref, the same
    # machinery `check` uses. --dry-run keeps it offline (no backend).
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        tdp = Path(td)
        subprocess.run(["git", "init"], cwd=td, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"], cwd=td, check=True, capture_output=True
        )
        subprocess.run(["git", "config", "user.name", "T"], cwd=td, check=True, capture_output=True)
        (tdp / "pyproject.toml").write_text("[project]\nname = 't'\n")
        (tdp / "unchanged.py").write_text('"""M."""\n\n\ndef untouched_fn(x):\n    """Old."""\n')
        subprocess.run(["git", "add", "."], cwd=td, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=td, check=True, capture_output=True)

        (tdp / "touched.py").write_text('"""M."""\n\n\ndef changed_fn(x):\n    """New."""\n')
        subprocess.run(["git", "add", "touched.py"], cwd=td, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add"], cwd=td, check=True, capture_output=True)

        result = runner.invoke(
            main,
            ["semantic", "--changed-only", "HEAD~1", "--min-tier", "1", "--dry-run", str(tdp)],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    assert "changed_fn" in result.output
    assert "untouched_fn" not in result.output


def test_semantic_real_run_with_fake_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    reply = json.dumps(
        {"findings": [{"name": "do_thing", "verdict": "weak", "issues": ["x>0 not stated"]}]}
    )
    monkeypatch.setattr("docpact.cli.make_backend", lambda cfg: _FakeBackend(reply))
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        Path(td, "m.py").write_text(_SRC)
        result = runner.invoke(main, ["semantic", "m.py", "--min-tier", "2"])
    assert result.exit_code == 1  # advisory finding → non-zero unless --exit-zero
    assert "SEM001" in result.output
    assert "x>0 not stated" in result.output


def test_semantic_exit_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    reply = json.dumps(
        {"findings": [{"name": "do_thing", "verdict": "empty", "issues": ["nothing"]}]}
    )
    monkeypatch.setattr("docpact.cli.make_backend", lambda cfg: _FakeBackend(reply))
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        Path(td, "m.py").write_text(_SRC)
        result = runner.invoke(main, ["semantic", "m.py", "--min-tier", "2", "--exit-zero"])
    assert result.exit_code == 0
    assert "SEM001" in result.output


_PYPROJECT_MODEL = '[tool.docpact.semantic]\nmodel = "gpt-4o-test"\n'


def test_semantic_provenance_in_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """Text output records the (model, prompt-fingerprint) pair a run used (ADR-015)."""
    reply = json.dumps({"findings": [{"name": "do_thing", "verdict": "weak", "issues": ["x"]}]})
    monkeypatch.setattr("docpact.cli.make_backend", lambda cfg: _FakeBackend(reply))
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        Path(td, "pyproject.toml").write_text(_PYPROJECT_MODEL)
        Path(td, "m.py").write_text(_SRC)
        result = runner.invoke(main, ["semantic", "m.py", "--min-tier", "2", "--exit-zero"])
    assert "provenance: model=gpt-4o-test;" in result.output
    expected_fp = analyzer.prompt_fingerprint(analyzer.SYSTEM)
    assert f"SEM001=builtin:{expected_fp}" in result.output


def test_semantic_provenance_in_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """JSON output carries provenance under the additive `meta.semantic` key."""
    reply = json.dumps({"findings": [{"name": "do_thing", "verdict": "weak", "issues": ["x"]}]})
    monkeypatch.setattr("docpact.cli.make_backend", lambda cfg: _FakeBackend(reply))
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        Path(td, "pyproject.toml").write_text(_PYPROJECT_MODEL)
        Path(td, "m.py").write_text(_SRC)
        result = runner.invoke(
            main, ["semantic", "m.py", "--min-tier", "2", "--exit-zero", "--format", "json"]
        )
    doc = json.loads(result.output)
    assert doc["meta"]["semantic"]["model"] == "gpt-4o-test"
    expected_fp = analyzer.prompt_fingerprint(analyzer.SYSTEM)
    assert doc["meta"]["semantic"]["prompts"]["SEM001"] == f"builtin:{expected_fp}"


def test_semantic_backend_error_is_usage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(cfg: object) -> object:
        raise backend.SemanticError("no API key: set $OPENAI_API_KEY")

    monkeypatch.setattr("docpact.cli.make_backend", boom)
    runner = CliRunner()
    with runner.isolated_filesystem() as td:
        Path(td, "m.py").write_text(_SRC)
        result = runner.invoke(main, ["semantic", "m.py", "--min-tier", "2"])
    assert result.exit_code == 2  # click.UsageError
    assert "no API key" in result.output


def test_system_prompt_guards_against_issue_11_false_positives() -> None:
    """The SYSTEM prompt must keep the clauses that fixed issue #11.

    Regression guard (the real-model behaviour can't be unit-tested): SEM must
    not penalise canonical-empty sections (DOC013's required form) and must make
    a weak/empty verdict cite the offending span, so a substantive Returns that
    opens with a noun phrase / "Does not return a value" is not mis-flagged.
    """
    assert "Raises: None." in analyzer.SYSTEM  # canonical-empty is correct, never flagged
    assert "Does not return a value" in analyzer.SYSTEM  # side-effecting None-returns are GOOD
    assert "quote" in analyzer.SYSTEM.lower()  # evidence rule: cite the span or verdict is good

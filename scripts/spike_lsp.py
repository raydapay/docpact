"""SPIKE — cross-file resolution via an LSP server (ty). THROWAWAY, not shipped.

Tests the one primitive docpact would need for cross-file rules: given a reference
to an IMPORTED symbol, can a language server resolve it to its defining file via
`textDocument/definition`? If yes, docpact stays per-file + AST-based and delegates
*only* import resolution to any LSP-conformant server — ty today, pyright/pylsp/jedi
tomorrow. No bespoke API; provider-agnostic, the same pluggability as the SEM backend.
See ADR-006.

It exercises the realistic adopter shape across scenarios:
  1. direct import, symbol used as a call kwarg value  (input_model=Imported)
  2. re-export chain (pkg/__init__ re-exports schemas.X), same kwarg-value reference

For each, it starts an LSP server over stdio, opens the workspace, fires
go-to-definition at the imported reference, and reports whether it resolved to the
class's true definition file. Resolving the class *fields* is docpact's own AST job —
this validates only the cross-file *location* resolution, which docpact can't do itself.

Usage:
    uv run python scripts/spike_lsp.py
    TY_SERVER_CMD="ty server" uv run python scripts/spike_lsp.py
    TY_SERVER_CMD="pyright-langserver --stdio" uv run python scripts/spike_lsp.py  # any LSP server
"""

from __future__ import annotations

import json
import os
import queue
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory


def _frame(obj: dict) -> bytes:
    """Serialize a JSON-RPC message with an LSP Content-Length header."""
    data = json.dumps(obj).encode("utf-8")
    return f"Content-Length: {len(data)}\r\n\r\n".encode() + data


def _reader(stdout, q: queue.Queue) -> None:
    """Read framed LSP messages off the server's stdout into a queue (thread)."""
    while True:
        headers: dict[bytes, bytes] = {}
        line = stdout.readline()
        if not line:
            q.put(None)
            return
        while line not in (b"\r\n", b"\n"):
            if b":" in line:
                k, _, v = line.partition(b":")
                headers[k.strip().lower()] = v.strip()
            line = stdout.readline()
            if not line:
                q.put(None)
                return
        n = int(headers.get(b"content-length", b"0"))
        body = stdout.read(n) if n else b""
        try:
            q.put(json.loads(body))
        except json.JSONDecodeError:
            pass


def _await(q: queue.Queue, msg_id: int, timeout: float = 20.0) -> dict:
    """Wait for the JSON-RPC response with msg_id, discarding notifications."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            msg = q.get(timeout=max(0.01, deadline - time.monotonic()))
        except queue.Empty:
            break
        if msg is None:
            raise RuntimeError("LSP server closed the connection")
        if msg.get("id") == msg_id and ("result" in msg or "error" in msg):
            return msg
    raise TimeoutError(f"no response for request id {msg_id} within {timeout}s")


def _definition(server_cmd: list[str], root: Path, query_file: Path, line: int, char: int) -> object:
    """Start the LSP server over a workspace, fire go-to-definition, return the raw result."""
    proc = subprocess.Popen(
        server_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    assert proc.stdin and proc.stdout
    q: queue.Queue = queue.Queue()
    threading.Thread(target=_reader, args=(proc.stdout, q), daemon=True).start()

    def send(obj: dict) -> None:
        proc.stdin.write(_frame(obj))
        proc.stdin.flush()

    try:
        send({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "processId": os.getpid(), "rootUri": root.as_uri(), "capabilities": {},
                "workspaceFolders": [{"uri": root.as_uri(), "name": "spike"}],
            },
        })
        if "error" in _await(q, 1):
            raise RuntimeError("initialize returned an error")
        send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        for path in sorted(root.rglob("*.py")):
            send({
                "jsonrpc": "2.0", "method": "textDocument/didOpen",
                "params": {"textDocument": {
                    "uri": path.as_uri(), "languageId": "python", "version": 1,
                    "text": path.read_text(),
                }},
            })
        time.sleep(1.0)  # let the server index the workspace
        send({
            "jsonrpc": "2.0", "id": 2, "method": "textDocument/definition",
            "params": {"textDocument": {"uri": query_file.as_uri()},
                       "position": {"line": line, "character": char}},
        })
        return _await(q, 2).get("result")
    finally:
        try:
            send({"jsonrpc": "2.0", "id": 9, "method": "shutdown", "params": None})
            _await(q, 9, timeout=5)
            send({"jsonrpc": "2.0", "method": "exit", "params": None})
        except (TimeoutError, RuntimeError, OSError):
            pass
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


_TOOLS_TEMPLATE = """\
from {pkg} import SearchTransactionsInput


class ToolSpec:
    def __init__(self, input_model):
        self.input_model = input_model


TOOLS = [ToolSpec(input_model=SearchTransactionsInput)]
"""

_MODEL = "class SearchTransactionsInput:\n    source: str\n    limit: int\n"


def _run_scenario(server_cmd: list[str], name: str, files: dict[str, str], def_suffix: str) -> bool:
    """Write a workspace, query the kwarg-value reference, report resolution."""
    with TemporaryDirectory() as td:
        root = Path(td)
        for rel, text in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        tools = root / "tools.py"
        lines = files["tools.py"].splitlines()
        ln = next(i for i, s in enumerate(lines) if "input_model=" in s)
        ch = lines[ln].index("SearchTransactionsInput", lines[ln].index("input_model="))

        result = _definition(server_cmd, root, tools, ln, ch)
        items = result if isinstance(result, list) else ([result] if result else [])
        uris = [it.get("uri") or it.get("targetUri", "") for it in items if isinstance(it, dict)]

        print(f"\n[{name}]  query tools.py:{ln}:{ch} (input_model=SearchTransactionsInput)")
        print(f"  result: {json.dumps(result)[:300]}")
        hit = next((u for u in uris if u.endswith(def_suffix)), None)
        if hit:
            print(f"  ✓ resolved to the true definition → …/{def_suffix}")
            return True
        if uris:
            print(f"  ~ resolved, but to {uris[0]} (not the def file {def_suffix} — a re-export hop)")
            return False
        print("  ✗ not resolved")
        return False


def main() -> int:
    """Run the LSP cross-file resolution scenarios and report a verdict."""
    server_cmd = shlex.split(os.environ.get("TY_SERVER_CMD", "ty server"))
    print(f"server: {server_cmd}")
    try:
        ok_direct = _run_scenario(
            server_cmd, "direct import + kwarg value",
            {"schemas.py": _MODEL, "tools.py": _TOOLS_TEMPLATE.format(pkg="schemas")},
            "schemas.py",
        )
        ok_reexport = _run_scenario(
            server_cmd, "re-export chain + kwarg value",
            {
                "pkg/__init__.py": "from pkg.schemas import SearchTransactionsInput\n",
                "pkg/schemas.py": _MODEL,
                "tools.py": _TOOLS_TEMPLATE.format(pkg="pkg"),
            },
            "schemas.py",
        )
    except (FileNotFoundError, RuntimeError, TimeoutError) as exc:
        print(f"\nFAILED: {exc}\n  (is `ty server` the right command? set TY_SERVER_CMD.)", file=sys.stderr)
        return 2

    print(f"\nsummary: direct={'ok' if ok_direct else 'NO'}  re-export={'ok' if ok_reexport else 'NO'}")
    return 0 if (ok_direct and ok_reexport) else 1


if __name__ == "__main__":
    sys.exit(main())

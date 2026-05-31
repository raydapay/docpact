"""A fake LSP server over stdio for tests — pure Python, no type checker.

Speaks just enough framed JSON-RPC to exercise the real LSPClient lifecycle
(spawn → initialize → didOpen → definition → shutdown/exit) without a real
language server, so CI stays offline and deterministic (ADR-009 invariant).

Behavior is selected by argv[1] (a mode); argv[2], if present, is the URI that
``definition`` resolves to (so a test can point at a real fixture file):

    initialize-error  initialize responds with a JSON-RPC error
    location          definition returns a single Location
    location-list     definition returns a one-element list of Location
    locationlink      definition returns a single LocationLink
    empty             definition always returns null (unresolved)
    delayed           definition returns null once, then a Location
    error             definition responds with a JSON-RPC error
    hang              definition never responds (exercises the client timeout)

Not shipped; lives under tests/fixtures/ (excluded from docpact + ruff).
"""

from __future__ import annotations

import json
import sys

_DEF_URI = "file:///workspace/schemas.py"


def _location(uri: str) -> dict:
    """A Location pointing at uri."""
    return {
        "uri": uri,
        "range": {"start": {"line": 5, "character": 6}, "end": {"line": 5, "character": 30}},
    }


def _locationlink(uri: str) -> dict:
    """A LocationLink pointing at uri."""
    return {
        "targetUri": uri,
        "targetRange": {"start": {"line": 5, "character": 0}, "end": {"line": 7, "character": 0}},
        "targetSelectionRange": {
            "start": {"line": 5, "character": 6},
            "end": {"line": 5, "character": 30},
        },
    }


def _read_message() -> dict | None:
    """Read one framed JSON-RPC message from stdin, or None at EOF."""
    stdin = sys.stdin.buffer
    headers: dict[bytes, bytes] = {}
    line = stdin.readline()
    if not line:
        return None
    while line not in (b"\r\n", b"\n"):
        if b":" in line:
            k, _, v = line.partition(b":")
            headers[k.strip().lower()] = v.strip()
        line = stdin.readline()
        if not line:
            return None
    n = int(headers.get(b"content-length", b"0"))
    body = stdin.read(n) if n else b""
    return json.loads(body)


def _send(obj: dict) -> None:
    """Frame and write a JSON-RPC message to stdout."""
    data = json.dumps(obj).encode("utf-8")
    out = sys.stdout.buffer
    out.write(f"Content-Length: {len(data)}\r\n\r\n".encode())
    out.write(data)
    out.flush()


def _definition_result(mode: str, definition_calls: int, uri: str) -> object:
    """Return the definition result for a mode, given the call count so far."""
    if mode in ("empty", "hang"):
        return None
    if mode == "delayed":
        return None if definition_calls == 1 else _location(uri)
    if mode == "location-list":
        return [_location(uri)]
    if mode == "locationlink":
        return _locationlink(uri)
    return _location(uri)


def main() -> int:
    """Run the fake server loop until exit."""
    mode = sys.argv[1] if len(sys.argv) > 1 else "location"
    target_uri = sys.argv[2] if len(sys.argv) > 2 else _DEF_URI
    if mode == "stderr-noise":
        # Emit a diagnostic line to stderr to exercise --lsp-log capture, then
        # behave like the default "location" mode.
        sys.stderr.write("fake-server: Confusing indentation for continuation line\n")
        sys.stderr.flush()
        mode = "location"
    definition_calls = 0
    while True:
        msg = _read_message()
        if msg is None:
            return 0
        method = msg.get("method")
        msg_id = msg.get("id")
        if method == "initialize":
            if mode == "initialize-error":
                _send(
                    {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32603, "message": "boom"}}
                )
            else:
                _send({"jsonrpc": "2.0", "id": msg_id, "result": {"capabilities": {}}})
        elif method == "textDocument/definition":
            definition_calls += 1
            if mode == "error":
                _send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32603, "message": "no"}})
            elif mode == "hang":
                continue  # never respond
            else:
                _send(
                    {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": _definition_result(mode, definition_calls, target_uri),
                    }
                )
        elif method == "shutdown":
            _send({"jsonrpc": "2.0", "id": msg_id, "result": None})
        elif method == "exit":
            return 0
        # initialized / didOpen and any other notification: ignored.


if __name__ == "__main__":
    sys.exit(main())

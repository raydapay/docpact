"""Provider-agnostic LSP client (ADR-009).

Graduates the cross-file resolution spike (`scripts/spike_lsp.py`) into a
shipped client. It spawns a configured language server, performs the
`initialize`/`initialized` handshake, opens documents, and asks
`textDocument/definition` to resolve an imported symbol to its defining file.
The wire details — Content-Length framing, the JSON-RPC reader thread,
`Location` vs `LocationLink` normalization, clean `shutdown`/`exit` — are all
isolated here, so downstream rule code only ever sees `LspLocation` values.

Every failure mode surfaces as `LSPError` with a human-readable cause: a
missing server binary, a hung server (timeout), or a malformed response. The
client never raises a bare transport exception across its public surface, so a
caller can degrade gracefully when cross-file analysis is unavailable.

The default server is ty (`["ty", "server"]`); any LSP-conformant server is a
config swap. See `[tool.docpact.lsp]` and ADR-009.
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
    from types import TracebackType


class LSPError(Exception):
    """An LSP-client failure (missing server, timeout, or bad response).

    Carries a human-readable cause so the CLI can print actionable guidance —
    e.g. "is the configured server installed?" — rather than a traceback. It is
    the single exception type crossing the client's public surface; transport
    errors (`OSError`, `TimeoutError`, `json` errors) are wrapped into it.

    Stability: beta
    """


@dataclass(frozen=True, slots=True)
class LspLocation:
    """A source location resolved by the server, normalized across wire shapes.

    The protocol returns either a `Location` (`uri` + `range`) or a
    `LocationLink` (`targetUri` + `targetRange`/`targetSelectionRange`); both
    collapse to this one shape. Positions are zero-based, matching the protocol
    and docpact's own column convention.

    Stability: beta
    """

    uri: str
    start_line: int
    start_char: int
    end_line: int
    end_char: int


def _frame(obj: dict[str, object]) -> bytes:
    """Serialize a JSON-RPC message with an LSP Content-Length header.

    Args:
        obj: The JSON-RPC message body.

    Returns:
        The header and body encoded as a single bytes payload ready to write
        to the server's stdin.
    """
    data = json.dumps(obj).encode("utf-8")
    return f"Content-Length: {len(data)}\r\n\r\n".encode() + data


def _reader(stdout: object, q: queue.Queue[dict[str, object] | None]) -> None:
    """Read framed LSP messages off the server's stdout into a queue.

    Runs on a daemon thread for the client's lifetime. Each decoded JSON-RPC
    message is placed on the queue; a sentinel ``None`` is enqueued when the
    stream closes so a waiting consumer learns the connection is gone.

    Args:
        stdout: The server process's stdout, a readable binary stream.
        q: Queue the decoded messages (and the closing sentinel) are placed on.
    """
    read = stdout.read  # ty: ignore[unresolved-attribute]
    readline = stdout.readline  # ty: ignore[unresolved-attribute]
    while True:
        headers: dict[bytes, bytes] = {}
        line = readline()
        if not line:
            q.put(None)
            return
        while line not in (b"\r\n", b"\n"):
            if b":" in line:
                k, _, v = line.partition(b":")
                headers[k.strip().lower()] = v.strip()
            line = readline()
            if not line:
                q.put(None)
                return
        n = int(headers.get(b"content-length", b"0"))
        body = read(n) if n else b""
        with contextlib.suppress(json.JSONDecodeError):
            q.put(json.loads(body))


def _normalize_locations(result: object) -> list[LspLocation]:
    """Normalize a textDocument/definition result into LspLocation values.

    The result may be ``null``, a single `Location`/`LocationLink`, or a list
    of either. Each item's URI comes from ``uri`` or ``targetUri``; its range
    from ``range``, ``targetSelectionRange``, or ``targetRange``. Items lacking
    a URI are dropped.

    Args:
        result: The raw ``result`` field of the definition response.

    Returns:
        Zero or more resolved locations, in the order the server returned them.
    """
    if result is None:
        items: list[object] = []
    elif isinstance(result, list):
        items = list(result)
    else:
        items = [result]

    locations: list[LspLocation] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        entry: dict[str, object] = {str(k): v for k, v in item.items()}
        uri = entry.get("uri") or entry.get("targetUri")
        if not isinstance(uri, str) or not uri:
            continue
        rng = entry.get("range") or entry.get("targetSelectionRange") or entry.get("targetRange")
        start = _position(rng, "start")
        end = _position(rng, "end")
        locations.append(
            LspLocation(
                uri=uri,
                start_line=start[0],
                start_char=start[1],
                end_line=end[0],
                end_char=end[1],
            )
        )
    return locations


def _position(rng: object, edge: str) -> tuple[int, int]:
    """Extract a (line, character) pair from a range's start/end, defaulting to 0.

    Args:
        rng: A range mapping (or anything; non-mappings yield zeros).
        edge: ``"start"`` or ``"end"``.

    Returns:
        The zero-based (line, character) pair, with 0 substituted for any
        missing or non-integer field.
    """
    if not isinstance(rng, dict):
        return (0, 0)
    point = {str(k): v for k, v in rng.items()}.get(edge)
    if not isinstance(point, dict):
        return (0, 0)
    coords: dict[str, object] = {str(k): v for k, v in point.items()}
    line = coords.get("line", 0)
    char = coords.get("character", 0)
    return (
        line if isinstance(line, int) else 0,
        char if isinstance(char, int) else 0,
    )


class LSPClient:
    """A context-managed client driving a language server over stdio.

    Use it as a context manager: entering spawns the server and completes the
    `initialize`/`initialized` handshake; exiting sends `shutdown`/`exit` and
    terminates the process. Within the block, `did_open` registers a document
    and `definition` resolves a position to its defining location(s).

    The client is single-threaded from the caller's side: requests are issued
    and awaited synchronously, while a background daemon thread drains the
    server's stdout. It is not safe to share one client across threads.

    Stability: beta
    """

    def __init__(self, server_cmd: tuple[str, ...], root: Path, *, timeout: float = 15.0) -> None:
        """Configure the server command, workspace root, and request timeout.

        Args:
            server_cmd: The language-server command and its arguments, e.g.
                ``("ty", "server")``. Must be non-empty.
            root: The workspace root directory, sent as ``rootUri`` so the
                server can index the project.
            timeout: Seconds to wait for a single response, and the overall
                budget for the definition readiness retry. Must be positive.

        Raises:
            LSPError: ``server_cmd`` is empty.

        Stability: beta
        """
        if not server_cmd:
            raise LSPError("server command is empty; set [tool.docpact.lsp] server")
        self._cmd = list(server_cmd)
        self._root = root
        self._timeout = timeout
        self._proc: subprocess.Popen[bytes] | None = None
        self._queue: queue.Queue[dict[str, object] | None] = queue.Queue()
        self._next_id = 0

    def __enter__(self) -> LSPClient:
        """Spawn the server and perform the initialize handshake.

        Returns:
            The ready client.

        Raises:
            LSPError: The server binary is missing, or initialize failed.

        Stability: beta
        """
        self._spawn()
        self._initialize()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Shut the server down cleanly, never masking a body exception.

        Args:
            exc_type: Exception type raised in the body, if any.
            exc: Exception instance raised in the body, if any.
            tb: Traceback of the body exception, if any.

        Stability: beta
        """
        self._shutdown()

    def _spawn(self) -> None:
        """Start the server subprocess and the stdout reader thread."""
        try:
            self._proc = subprocess.Popen(
                self._cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, ValueError) as exc:
            raise LSPError(
                f"could not start LSP server {self._cmd!r}: {exc}. "
                f"Is it installed? Configure [tool.docpact.lsp] server."
            ) from exc
        if self._proc.stdin is None or self._proc.stdout is None:
            raise LSPError("LSP server did not provide stdio pipes")
        threading.Thread(target=_reader, args=(self._proc.stdout, self._queue), daemon=True).start()

    def _send(self, obj: dict[str, object]) -> None:
        """Frame and write a JSON-RPC message to the server's stdin."""
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise LSPError("LSP server is not running")
        try:
            proc.stdin.write(_frame(obj))
            proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise LSPError(f"failed to write to LSP server: {exc}") from exc

    def _await(self, msg_id: int, timeout: float) -> dict[str, object]:
        """Wait for the response with msg_id, discarding interleaved notifications.

        Args:
            msg_id: The JSON-RPC id whose response is awaited.
            timeout: Maximum seconds to wait.

        Returns:
            The matching response message.

        Raises:
            LSPError: The server closed the connection.
            TimeoutError: No matching response arrived within the timeout.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                msg = self._queue.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            if msg is None:
                raise LSPError("LSP server closed the connection")
            if msg.get("id") == msg_id and ("result" in msg or "error" in msg):
                return msg
        raise TimeoutError(f"no response for request id {msg_id} within {timeout}s")

    def _request(self, method: str, params: dict[str, object], timeout: float) -> object:
        """Issue a JSON-RPC request and return its ``result``.

        Args:
            method: The LSP method name.
            params: The request parameters.
            timeout: Seconds to wait for the response.

        Returns:
            The response's ``result`` field.

        Raises:
            LSPError: The server returned an error, hung (timeout), or closed.
        """
        self._next_id += 1
        msg_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
        try:
            msg = self._await(msg_id, timeout)
        except TimeoutError as exc:
            raise LSPError(f"LSP server did not respond to {method!r}: {exc}") from exc
        if "error" in msg:
            raise LSPError(f"LSP server returned an error for {method!r}: {msg['error']}")
        return msg.get("result")

    def _initialize(self) -> None:
        """Perform the initialize request and send the initialized notification."""
        self._request(
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": self._root.as_uri(),
                "capabilities": {},
                "workspaceFolders": [{"uri": self._root.as_uri(), "name": "docpact"}],
            },
            self._timeout,
        )
        self._send({"jsonrpc": "2.0", "method": "initialized", "params": {}})

    def did_open(self, path: Path) -> None:
        """Register a document with the server by sending its current contents.

        Args:
            path: The Python file to open. Its text is read from disk and sent
                in a ``textDocument/didOpen`` notification.

        Raises:
            LSPError: The file could not be read, or the server is not running.

        Stability: beta
        """
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise LSPError(f"could not read {path}: {exc}") from exc
        self._send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": path.as_uri(),
                        "languageId": "python",
                        "version": 1,
                        "text": text,
                    }
                },
            }
        )

    def definition(self, file: Path, line: int, char: int) -> list[LspLocation]:
        """Resolve the symbol at a position to its defining location(s).

        Fires ``textDocument/definition`` at the given zero-based position. To
        tolerate a server still indexing the workspace, an empty result is
        retried with a short backoff until a non-empty result arrives or the
        client's ``timeout`` budget is exhausted; an empty list is then a real
        "unresolved", not a premature one.

        Args:
            file: The file containing the reference being resolved.
            line: Zero-based line of the reference.
            char: Zero-based character offset of the reference.

        Returns:
            The resolved locations (empty if the symbol does not resolve),
            normalized across `Location`/`LocationLink` wire shapes.

        Raises:
            LSPError: The server hung, errored, or closed the connection.

        Stability: beta
        """
        params: dict[str, object] = {
            "textDocument": {"uri": file.as_uri()},
            "position": {"line": line, "character": char},
        }
        deadline = time.monotonic() + self._timeout
        while True:
            remaining = deadline - time.monotonic()
            result = self._request("textDocument/definition", params, max(0.05, remaining))
            locations = _normalize_locations(result)
            if locations or time.monotonic() >= deadline:
                return locations
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

    def _shutdown(self) -> None:
        """Send shutdown/exit and terminate the process, swallowing teardown errors."""
        proc = self._proc
        if proc is None:
            return
        try:
            self._send({"jsonrpc": "2.0", "id": -1, "method": "shutdown", "params": None})
            self._await(-1, timeout=min(5.0, self._timeout))
            self._send({"jsonrpc": "2.0", "method": "exit", "params": None})
        except (LSPError, TimeoutError, OSError):
            pass
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        self._proc = None

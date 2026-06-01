"""Pluggable LLM backend for semantic analysis (ADR-008).

The analyzer is backend-agnostic: it builds a system + user prompt and parses a
text reply. All provider variation is isolated behind one tiny protocol:

    LLMBackend.complete(system, user) -> str   # the model's text reply

Adding a new provider (Gemini-native, Anthropic-native, a non-OpenAI local shape)
is a single new class implementing that protocol plus one line in `make_backend`.
Nothing in the analyzer or the CLI changes.

One adapter ships: ``OpenAICompatBackend``, which speaks the OpenAI
chat-completions wire format and therefore covers GitHub Models, OpenAI,
OpenRouter, Azure OpenAI, and local OpenAI-compatible servers (Ollama, vLLM,
llama.cpp) — selected purely by ``api_base`` / ``model`` / ``api_key_env``.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable

    from docpact.config import SemanticConfig


class SemanticError(Exception):
    """A semantic-backend failure (auth, network, rate limit, bad response).

    Carries a human-readable cause so the CLI can print actionable guidance
    rather than a traceback.
    """


@runtime_checkable
class LLMBackend(Protocol):
    """A minimal text-in, text-out LLM adapter.

    Implementations translate a (system, user) prompt pair into a provider call
    and return the model's reply as plain text. They do not parse it — JSON
    parsing is the analyzer's job, so the protocol stays provider-agnostic.

    Stability: beta
    """

    def complete(self, system: str, user: str) -> str:
        """Return the model's text reply to a system + user prompt.

        Args:
            system: The system instruction (role and output contract).
            user: The user message (the functions to review).

        Returns:
            The model's reply as text. The analyzer parses it as JSON.

        Raises:
            SemanticError: The provider call failed (auth, network, rate
                limit, or an unexpected response shape).

        Stability: beta
        """
        ...


class OpenAICompatBackend:
    """LLM backend speaking the OpenAI chat-completions wire format.

    Works against any OpenAI-compatible endpoint — GitHub Models, OpenAI,
    OpenRouter, Azure, and local servers (Ollama, vLLM, llama.cpp) — by varying
    ``api_base`` and ``model``. Uses stdlib ``urllib`` only; no third-party
    dependency is added.

    Stability: beta
    """

    def __init__(
        self,
        *,
        api_base: str,
        model: str,
        api_key: str,
        timeout: float = 90.0,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Configure the endpoint, model, and credential for chat completions.

        Args:
            api_base: Base URL of the OpenAI-compatible API (without the
                ``/chat/completions`` suffix), e.g. the GitHub Models inference
                URL or ``http://localhost:11434/v1`` for Ollama.
            model: Model identifier as the endpoint expects it (e.g.
                ``openai/gpt-4o-mini`` for GitHub Models, ``gpt-4o-mini`` for
                OpenAI, ``llama3.1`` for Ollama).
            api_key: Bearer token sent in the Authorization header.
            timeout: Per-request timeout in seconds.
            max_retries: Maximum retries on transient failures (HTTP 429/5xx and
                transport errors) before giving up, using capped exponential
                backoff. 0 disables retrying. Auth (401/403) and bad-request
                (4xx other than 429) failures are never retried.
            sleep: Injection point for the backoff sleep; defaults to
                ``time.sleep``. Tests pass a no-op to avoid real delays.

        Stability: beta
        """
        self._url = api_base.rstrip("/") + "/chat/completions"
        self._model = model
        self._key = api_key
        self._timeout = timeout
        self._max_retries = max_retries
        self._sleep = sleep

    @staticmethod
    def _backoff_seconds(attempt: int) -> float:
        """Return the backoff delay before retry ``attempt`` (0-based), capped.

        Args:
            attempt: The zero-based index of the failed attempt just made.

        Returns:
            Seconds to wait: exponential (1s, 2s, 4s, …) capped at 8s.
        """
        return min(2.0**attempt, 8.0)

    def complete(self, system: str, user: str) -> str:
        """Send one chat completion and return the assistant's text reply.

        Args:
            system: The system instruction.
            user: The user message.

        Returns:
            The assistant message content as text.

        Raises:
            SemanticError: The request failed or the response was malformed.
                401/403 indicate a bad or under-scoped credential; 429 a rate
                limit; other codes carry the server's error body.

        Stability: beta
        """
        payload = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        attempt = 0
        while True:
            req = urllib.request.Request(
                self._url,
                data=data,
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                if exc.code in (401, 403):
                    raise SemanticError(
                        f"auth failed (HTTP {exc.code}); check the credential in the "
                        f"configured api_key_env has access: {detail}"
                    ) from exc
                # 429 (rate limit) and 5xx (server) are transient — retry with backoff.
                if (exc.code == 429 or 500 <= exc.code < 600) and attempt < self._max_retries:
                    self._sleep(self._backoff_seconds(attempt))
                    attempt += 1
                    continue
                label = "rate-limited (HTTP 429)" if exc.code == 429 else f"HTTP {exc.code}"
                tries = f" after {attempt + 1} attempt(s)" if attempt else ""
                raise SemanticError(f"{label}{tries}: {detail}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < self._max_retries:
                    self._sleep(self._backoff_seconds(attempt))
                    attempt += 1
                    continue
                tries = f" after {attempt + 1} attempt(s)" if attempt else ""
                raise SemanticError(f"backend transport error{tries}: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise SemanticError(f"backend transport error: {exc}") from exc
            try:
                return str(body["choices"][0]["message"]["content"])
            except (KeyError, IndexError, TypeError) as exc:
                raise SemanticError(f"unexpected response shape: {json.dumps(body)[:300]}") from exc


def make_backend(config: SemanticConfig) -> LLMBackend:
    """Build the configured LLM backend, reading the API key from the environment.

    Args:
        config: The resolved ``[tool.docpact.semantic]`` configuration.

    Returns:
        An LLMBackend ready to call.

    Raises:
        SemanticError: The backend name is unknown, the API key environment
            variable is unset, or a required field (api_base/model) is missing.

    Constraints:
        Only the ``openai-compat`` backend is implemented. Adding another
        provider means a new adapter class and one branch here — see ADR-008.

    Stability: beta
    """
    api_key = os.environ.get(config.api_key_env, "")
    if not api_key:
        raise SemanticError(
            f"no API key: set ${config.api_key_env} (or change "
            f"[tool.docpact.semantic] api_key_env)."
        )
    if config.backend == "openai-compat":
        if not config.api_base:
            raise SemanticError("[tool.docpact.semantic] api_base is required for openai-compat.")
        if not config.model:
            raise SemanticError("[tool.docpact.semantic] model is required.")
        return OpenAICompatBackend(
            api_base=config.api_base,
            model=config.model,
            api_key=api_key,
            max_retries=config.max_retries,
        )
    raise SemanticError(
        f"unknown backend {config.backend!r}; only 'openai-compat' is implemented. "
        f"Add an adapter class in docpact.semantic.backend for a new provider (ADR-008)."
    )

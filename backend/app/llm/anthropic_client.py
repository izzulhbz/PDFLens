"""Answers from the Anthropic API (Claude).

The API key is read from the environment by the backend and never sent to
the browser: the frontend only ever sees provider names and answers.
"""

import threading
import time
from typing import Any

import anthropic

from app.llm.base import JsonSchema, LLMError

# Checking availability calls the API, so the result is reused for a while
# instead of costing a request every time the UI loads the provider list.
AVAILABILITY_CACHE_SECONDS = 60.0


class AnthropicClient:
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout_seconds: float = 10.0,
        max_tokens: int = 4096,  # room for a detailed summary with charts
        sdk_client: Any = None,
    ) -> None:
        self._configured = bool(api_key)
        self._model = model
        self._timeout = timeout_seconds
        self._max_tokens = max_tokens
        # max_retries=0: the SDK would otherwise retry failed calls itself,
        # so a "10 second" timeout could really take 30+ seconds before the
        # router gets the chance to fall back to Ollama.
        self._client = sdk_client or anthropic.Anthropic(
            api_key=api_key or "not-configured", timeout=timeout_seconds, max_retries=0
        )
        self._lock = threading.Lock()
        self._cached: tuple[float, tuple[bool, str]] | None = None

    @property
    def configured(self) -> bool:
        return self._configured

    def generate(self, system: str, user: str, *, json_schema: JsonSchema | None = None) -> str:
        if not self._configured:
            raise LLMError("ANTHROPIC_API_KEY is not set", can_fall_back=True)
        # The schema itself isn't sent: the system prompt describes the JSON
        # shape, Claude follows it reliably, and the caller validates the
        # result anyway. A structured reply (a document summary) is much
        # longer than a short answer, so it gets more time than the 10 s
        # that keeps interactive questions responsive.
        timeout = self._timeout if json_schema is None else max(self._timeout, 60.0)
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                timeout=timeout,
            )
        except anthropic.APIConnectionError as exc:  # includes timeouts
            raise LLMError(
                f"Anthropic unreachable: {type(exc).__name__}", can_fall_back=True
            ) from exc
        except anthropic.APIStatusError as exc:
            # 5xx (including 529 "overloaded") and 429 are temporary outages.
            # Other 4xx codes mean our request or key is wrong.
            temporary = exc.status_code >= 500 or exc.status_code == 429
            raise LLMError(
                f"Anthropic returned HTTP {exc.status_code}", can_fall_back=temporary
            ) from exc

        # The reply is a list of content blocks; only text blocks matter here.
        text = "".join(
            getattr(block, "text", "") for block in message.content if block.type == "text"
        ).strip()
        if not text:
            raise LLMError("Anthropic returned no text", can_fall_back=True)
        return text

    def availability(self) -> tuple[bool, str]:
        if not self._configured:
            return False, "No API key configured"
        with self._lock:
            if self._cached and time.monotonic() - self._cached[0] < AVAILABILITY_CACHE_SECONDS:
                return self._cached[1]
        try:
            # Listing models is free and proves both that the API is
            # reachable and that the key is accepted.
            self._client.models.list(limit=1)
            result = (True, "Reachable")
        except anthropic.AuthenticationError:
            result = (False, "API key rejected")
        except anthropic.APIError:
            result = (False, "Unreachable")
        with self._lock:
            self._cached = (time.monotonic(), result)
        return result

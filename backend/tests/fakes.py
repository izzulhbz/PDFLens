"""Test doubles for LLM providers and the Anthropic SDK."""

from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2

_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


class ScriptedLLM:
    """An LLMClient that returns a fixed answer (or raises) and records every prompt."""

    def __init__(
        self,
        name: str,
        answer: str = "Scripted answer [p. 1]",
        *,
        error: Exception | None = None,
        available: bool = True,
    ) -> None:
        self.name = name
        self.answer = answer
        self.error = error
        self.available = available
        self.calls: list[tuple[str, str]] = []
        self.schemas: list[dict[str, Any] | None] = []

    def generate(self, system: str, user: str, *, json_schema: dict[str, Any] | None = None) -> str:
        self.calls.append((system, user))
        self.schemas.append(json_schema)
        if self.error is not None:
            raise self.error
        return self.answer

    def availability(self) -> tuple[bool, str]:
        return self.available, "scripted"


def anthropic_status_error(status: int) -> anthropic.APIStatusError:
    """A real SDK exception for an HTTP status, as the SDK itself would raise it."""
    classes: dict[int, type[anthropic.APIStatusError]] = {
        400: anthropic.BadRequestError,
        401: anthropic.AuthenticationError,
        429: anthropic.RateLimitError,
        500: anthropic.InternalServerError,
    }
    cls = classes.get(status, anthropic.APIStatusError)
    return cls(f"HTTP {status}", response=httpx2.Response(status, request=_REQUEST), body=None)


def anthropic_timeout() -> anthropic.APITimeoutError:
    return anthropic.APITimeoutError(request=_REQUEST)


class FakeAnthropicSDK:
    """Stands in for anthropic.Anthropic: same .messages.create / .models.list shape."""

    def __init__(self, text: str = "Claude says hi [p. 2]", error: Exception | None = None):
        self.create_calls: list[dict[str, Any]] = []
        self.list_calls = 0
        self.list_error: Exception | None = None
        self._text, self._error = text, error
        self.messages = SimpleNamespace(create=self._create)
        self.models = SimpleNamespace(list=self._list)

    def _create(self, **kwargs: Any) -> Any:
        self.create_calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self._text)])

    def _list(self, **kwargs: Any) -> Any:
        self.list_calls += 1
        if self.list_error is not None:
            raise self.list_error
        return []

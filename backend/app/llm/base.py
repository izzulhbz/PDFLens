"""The LLMClient interface: one method that turns a prompt into an answer.

The ask endpoint, the router and the evaluation harness only know this
interface, so Anthropic, Ollama and the fake used in tests are
interchangeable. Model names come from configuration, never from the code.
"""

from typing import Protocol

from app.config import LLM_PROVIDERS as PROVIDERS

__all__ = ["PROVIDERS", "LLMClient", "LLMError"]


class LLMError(Exception):
    """A call to an LLM failed.

    `can_fall_back` says whether trying another provider makes sense: true
    for outages (connection errors, timeouts, 5xx, rate limits), false for
    our own mistakes (a bad request or an invalid API key), which another
    attempt would not fix.
    """

    def __init__(self, message: str, *, can_fall_back: bool) -> None:
        super().__init__(message)
        self.can_fall_back = can_fall_back


class LLMClient(Protocol):
    name: str  # "anthropic", "ollama" or "mock", stored in the audit log

    def generate(self, system: str, user: str) -> str:
        """Answer `user` following the instructions in `system`. Raises LLMError."""
        ...

    def availability(self) -> tuple[bool, str]:
        """(usable right now, short reason shown in the UI)."""
        ...

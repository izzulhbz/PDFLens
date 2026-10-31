"""Chooses which LLM answers a question: Anthropic, Ollama, or "auto".

- "anthropic" / "ollama": use exactly that provider. If it fails, the
  request fails; the user asked for it specifically, so silently answering
  with a different model would be misleading.
- "auto": prefer Anthropic (better answers), and fall back to Ollama (local,
  always there) when Anthropic has an outage: a connection error, timeout,
  5xx or 429. Errors that another attempt wouldn't fix, such as an invalid
  API key, are not hidden by a fallback. The circuit breaker skips
  Anthropic entirely while it keeps failing, and auto mode goes straight
  to Ollama when no API key is configured.

The answer always records which provider really produced it, so the UI and
the audit log never claim "anthropic" for an answer Ollama wrote.
"""

import logging
from dataclasses import dataclass

from app.llm.base import PROVIDERS, JsonSchema, LLMClient, LLMError
from app.llm.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoutedAnswer:
    text: str
    provider: str  # the provider that actually answered
    fell_back: bool


class LLMRouter:
    def __init__(
        self,
        anthropic: LLMClient,
        ollama: LLMClient,
        *,
        default: str,
        breaker: CircuitBreaker | None = None,
        anthropic_configured: bool = True,
    ) -> None:
        if default not in PROVIDERS:
            raise ValueError(f"Unknown default provider {default!r}")
        self.anthropic = anthropic
        self.ollama = ollama
        self.default = default
        self.breaker = breaker or CircuitBreaker()
        self.anthropic_configured = anthropic_configured

    def generate(
        self,
        system: str,
        user: str,
        requested: str | None = None,
        *,
        json_schema: JsonSchema | None = None,
    ) -> RoutedAnswer:
        provider = requested or self.default
        if provider == "anthropic":
            return self._call(self.anthropic, system, user, json_schema, fell_back=False)
        if provider == "ollama":
            return self._call(self.ollama, system, user, json_schema, fell_back=False)
        if provider == "auto":
            return self._auto(system, user, json_schema)
        raise ValueError(f"Unknown provider {provider!r}")

    def _auto(self, system: str, user: str, json_schema: JsonSchema | None) -> RoutedAnswer:
        if not self.anthropic_configured:
            return self._call(self.ollama, system, user, json_schema, fell_back=False)

        if self.breaker.allow_request():
            try:
                answer = self._call(self.anthropic, system, user, json_schema, fell_back=False)
            except LLMError as exc:
                if not exc.can_fall_back:
                    raise
                self.breaker.record_failure()
                logger.warning(
                    "llm.fallback from=anthropic to=ollama reason=%r breaker=%s",
                    str(exc),
                    self.breaker.state,
                )
            else:
                self.breaker.record_success()
                return answer
        else:
            logger.warning("llm.fallback from=anthropic to=ollama reason='circuit open'")

        return self._call(self.ollama, system, user, json_schema, fell_back=True)

    @staticmethod
    def _call(
        client: LLMClient,
        system: str,
        user: str,
        json_schema: JsonSchema | None,
        *,
        fell_back: bool,
    ) -> RoutedAnswer:
        text = client.generate(system, user, json_schema=json_schema)
        return RoutedAnswer(text, client.name, fell_back)

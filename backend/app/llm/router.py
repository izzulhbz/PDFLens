"""Chooses which LLM answers a question: Anthropic, Ollama GPU, Ollama, or "auto".

- "anthropic" / "ollama_gpu" / "ollama": use exactly that provider. If it
  fails, the request fails; the user asked for it specifically, so silently
  answering with a different model would be misleading.
- "auto": try the providers in order of answer quality and speed, falling
  through on outages (a connection error, timeout, 5xx or 429):
    1. Anthropic, when an API key is configured: the best answers.
    2. Ollama GPU, when configured: a larger local model on the host's GPU.
    3. Ollama: the small model in the Ollama container, always there.
  Errors that another attempt wouldn't fix, such as an invalid API key, are
  not hidden by a fallback. Each optional provider has its own circuit
  breaker, so auto mode skips one entirely while it keeps failing.

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
    fell_back: bool  # a provider earlier in the auto order failed or was skipped


class LLMRouter:
    def __init__(
        self,
        anthropic: LLMClient,
        ollama: LLMClient,
        *,
        default: str,
        breaker: CircuitBreaker | None = None,
        anthropic_configured: bool = True,
        ollama_gpu: LLMClient | None = None,
        gpu_breaker: CircuitBreaker | None = None,
    ) -> None:
        if default not in PROVIDERS:
            raise ValueError(f"Unknown default provider {default!r}")
        self.anthropic = anthropic
        self.ollama = ollama
        # None when OLLAMA_GPU_BASE_URL isn't set.
        self.ollama_gpu = ollama_gpu
        self.default = default
        self.breaker = breaker or CircuitBreaker()
        self.gpu_breaker = gpu_breaker or CircuitBreaker()
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
        if provider == "auto":
            return self._auto(system, user, json_schema)
        if provider == "anthropic":
            return self._call(self.anthropic, system, user, json_schema, fell_back=False)
        if provider == "ollama":
            return self._call(self.ollama, system, user, json_schema, fell_back=False)
        if provider == "ollama_gpu":
            if self.ollama_gpu is None:
                raise LLMError("Ollama GPU is not configured", can_fall_back=False)
            return self._call(self.ollama_gpu, system, user, json_schema, fell_back=False)
        raise ValueError(f"Unknown provider {provider!r}")

    def _auto(self, system: str, user: str, json_schema: JsonSchema | None) -> RoutedAnswer:
        # The optional providers in order, each with its breaker. The CPU
        # Ollama is the last resort and has no breaker: there's nothing
        # left to fall back to.
        chain: list[tuple[LLMClient, CircuitBreaker]] = []
        if self.anthropic_configured:
            chain.append((self.anthropic, self.breaker))
        if self.ollama_gpu is not None:
            chain.append((self.ollama_gpu, self.gpu_breaker))

        fell_back = False
        for position, (client, breaker) in enumerate(chain):
            next_name = chain[position + 1][0].name if position + 1 < len(chain) else "ollama"
            if not breaker.allow_request():
                logger.warning(
                    "llm.fallback from=%s to=%s reason='circuit open'", client.name, next_name
                )
                fell_back = True
                continue
            try:
                answer = self._call(client, system, user, json_schema, fell_back=fell_back)
            except LLMError as exc:
                if not exc.can_fall_back:
                    raise
                breaker.record_failure()
                logger.warning(
                    "llm.fallback from=%s to=%s reason=%r breaker=%s",
                    client.name,
                    next_name,
                    str(exc),
                    breaker.state,
                )
                fell_back = True
            else:
                breaker.record_success()
                return answer

        return self._call(self.ollama, system, user, json_schema, fell_back=fell_back)

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

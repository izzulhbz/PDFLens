"""Chooses which LLM answers a question: Anthropic, Ollama GPU, Ollama, or "auto".

- "anthropic" / "ollama_gpu" / "ollama": use exactly that provider. If it
  fails, the request fails; the user asked for it specifically, so silently
  answering with a different model would be misleading.
- "auto" (shown as "Default" in the UI): try the providers in turn, falling
  through on outages (a connection error, timeout, 5xx or 429). The
  standard order is by answer quality:
    1. Anthropic, when an API key is configured: the best answers.
    2. Ollama GPU, when configured: a larger local model on the host's GPU.
    3. Ollama: the small model in the Ollama container, always there.
  A request can name a preferred model ("prefer", the user's default
  model), which is then tried first, followed by the rest in that order.
  Errors that another attempt wouldn't fix, such as an invalid API key, are
  not hidden by a fallback. Each provider has its own circuit breaker, so
  auto mode skips one entirely while it keeps failing (except the last one
  left, which is always tried).

The answer always records which provider really produced it, so the UI and
the audit log never claim "anthropic" for an answer Ollama wrote.
"""

import logging
from dataclasses import dataclass

from app.llm.base import PROVIDERS, JsonSchema, LLMClient, LLMError
from app.llm.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

# The models auto mode can use, in its standard order.
MODELS = ("anthropic", "ollama_gpu", "ollama")


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
        self.ollama_breaker = CircuitBreaker()
        self.anthropic_configured = anthropic_configured

    def generate(
        self,
        system: str,
        user: str,
        requested: str | None = None,
        *,
        json_schema: JsonSchema | None = None,
        prefer: str | None = None,
    ) -> RoutedAnswer:
        """Answer with the requested provider. `prefer` only matters in auto mode."""
        provider = requested or self.default
        if provider == "auto":
            return self._auto(system, user, json_schema, prefer)
        if provider == "anthropic":
            return self._call(self.anthropic, system, user, json_schema, fell_back=False)
        if provider == "ollama":
            return self._call(self.ollama, system, user, json_schema, fell_back=False)
        if provider == "ollama_gpu":
            if self.ollama_gpu is None:
                raise LLMError("Ollama GPU is not configured", can_fall_back=False)
            return self._call(self.ollama_gpu, system, user, json_schema, fell_back=False)
        raise ValueError(f"Unknown provider {provider!r}")

    def auto_order(self, prefer: str | None = None) -> list[str]:
        """The configured models auto mode tries, in order."""
        if prefer is not None and prefer not in MODELS:
            raise ValueError(f"Unknown model {prefer!r}")
        order = [prefer, *(m for m in MODELS if m != prefer)] if prefer else list(MODELS)
        configured = {
            "anthropic": self.anthropic_configured,
            "ollama_gpu": self.ollama_gpu is not None,
            "ollama": True,
        }
        return [name for name in order if configured[name]]

    def _auto(
        self, system: str, user: str, json_schema: JsonSchema | None, prefer: str | None
    ) -> RoutedAnswer:
        chain = [self._client_and_breaker(name) for name in self.auto_order(prefer)]
        fell_back = False
        for position, (client, breaker) in enumerate(chain):
            last = position == len(chain) - 1
            next_name = "none" if last else chain[position + 1][0].name
            # The last provider left is tried even with its breaker open:
            # there's nothing to fall back to, and an error beats no attempt.
            if not last and not breaker.allow_request():
                logger.warning(
                    "llm.fallback from=%s to=%s reason='circuit open'", client.name, next_name
                )
                fell_back = True
                continue
            try:
                answer = self._call(client, system, user, json_schema, fell_back=fell_back)
            except LLMError as exc:
                if exc.can_fall_back:
                    breaker.record_failure()
                if last or not exc.can_fall_back:
                    raise
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
        raise LLMError("No provider configured", can_fall_back=False)  # unreachable: Ollama

    def _client_and_breaker(self, name: str) -> tuple[LLMClient, CircuitBreaker]:
        if name == "anthropic":
            return self.anthropic, self.breaker
        if name == "ollama_gpu" and self.ollama_gpu is not None:
            return self.ollama_gpu, self.gpu_breaker
        return self.ollama, self.ollama_breaker

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

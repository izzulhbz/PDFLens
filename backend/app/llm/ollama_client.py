"""Answers from a local Ollama model (POST /api/chat)."""

from typing import Any

import httpx

from app.llm.base import JsonSchema, LLMError
from app.ollama import has_model, list_models

CONTEXT_TOKENS = 8192


class OllamaClient:
    name = "ollama"

    def __init__(self, client: httpx.Client, model: str, *, timeout_seconds: float = 180.0) -> None:
        self._client = client
        self._model = model
        # Generous: on a CPU, a local model can take a minute for a long answer.
        self._timeout = timeout_seconds

    def generate(self, system: str, user: str, *, json_schema: JsonSchema | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "stream": False,
            "options": {
                # Temperature 0: the same question gets the same answer,
                # which makes behaviour and evaluation repeatable.
                "temperature": 0,
                # Room for the prompt and the reply. Ollama's default context
                # window is smaller and silently cuts off the start of long
                # prompts (such as a document summary's excerpts).
                "num_ctx": CONTEXT_TOKENS,
            },
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_schema is not None:
            # Structured output: Ollama constrains generation so the reply
            # is valid JSON of this shape, which small models otherwise get
            # wrong often.
            payload["format"] = json_schema
        try:
            response = self._client.post("/api/chat", json=payload, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise LLMError(
                f"Ollama unreachable: {type(exc).__name__}", can_fall_back=False
            ) from exc
        if response.status_code != 200:
            raise LLMError(f"Ollama returned HTTP {response.status_code}", can_fall_back=False)
        try:
            body: Any = response.json()
            text = str(body["message"]["content"]).strip()
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMError("Ollama returned an unexpected body", can_fall_back=False) from exc
        if not text:
            raise LLMError("Ollama returned no text", can_fall_back=False)
        return text

    def availability(self) -> tuple[bool, str]:
        try:
            models = list_models(self._client)
        except (httpx.HTTPError, ValueError):
            return False, "Ollama unreachable"
        if not has_model(self._model, models):
            return False, f"Model {self._model} not pulled"
        return True, "Reachable"

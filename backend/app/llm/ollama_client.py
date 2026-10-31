"""Answers from a local Ollama model (POST /api/chat)."""

from typing import Any

import httpx

from app.llm.base import LLMError
from app.ollama import has_model, list_models


class OllamaClient:
    name = "ollama"

    def __init__(self, client: httpx.Client, model: str, *, timeout_seconds: float = 180.0) -> None:
        self._client = client
        self._model = model
        # Generous: on a CPU, a local model can take a minute for a long answer.
        self._timeout = timeout_seconds

    def generate(self, system: str, user: str) -> str:
        try:
            response = self._client.post(
                "/api/chat",
                json={
                    "model": self._model,
                    "stream": False,
                    # Temperature 0: the same question gets the same answer,
                    # which makes behaviour and evaluation repeatable.
                    "options": {"temperature": 0},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=self._timeout,
            )
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

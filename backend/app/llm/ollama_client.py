"""Answers from a local Ollama model (POST /api/chat).

The same client serves two providers: "ollama", the model in the Ollama
container (CPU only), and "ollama_gpu", a model on an Ollama running
natively on the host, where it can use the GPU. Only the name, server and
model differ.
"""

from typing import Any

import httpx

from app.llm.base import JsonSchema, LLMError
from app.ollama import has_model, list_models

CONTEXT_TOKENS = 8192


class OllamaClient:
    def __init__(
        self,
        client: httpx.Client,
        model: str,
        *,
        timeout_seconds: float = 180.0,
        name: str = "ollama",
    ) -> None:
        self.name = name
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
        # Outages (unreachable, timeout, 5xx) and a missing model (404) can
        # fall back to another provider in auto mode; any other 4xx means
        # our request is wrong, which another provider wouldn't fix.
        try:
            response = self._client.post("/api/chat", json=payload, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise LLMError(
                f"{self.name} unreachable: {type(exc).__name__}", can_fall_back=True
            ) from exc
        if response.status_code != 200:
            raise LLMError(
                f"{self.name} returned HTTP {response.status_code}",
                can_fall_back=response.status_code >= 500 or response.status_code == 404,
            )
        try:
            body: Any = response.json()
            text = str(body["message"]["content"]).strip()
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMError(f"{self.name} returned an unexpected body", can_fall_back=True) from exc
        if not text:
            raise LLMError(f"{self.name} returned no text", can_fall_back=True)
        return text

    def availability(self) -> tuple[bool, str]:
        try:
            models = list_models(self._client)
        except (httpx.HTTPError, ValueError):
            return False, "Ollama unreachable"
        if not has_model(self._model, models):
            return False, f"Model {self._model} not pulled"
        if self.name == "ollama_gpu" and self._loaded_on_cpu():
            return True, "Reachable, but running on the CPU (see the README to enable the GPU)"
        return True, "Reachable"

    def _loaded_on_cpu(self) -> bool:
        """True if the model is in memory with none of it on a GPU.

        Ollama only reports this while the model is loaded (it unloads after
        5 idle minutes), so "not loaded" counts as fine.
        """
        try:
            loaded = self._client.get("/api/ps").json().get("models", [])
        except (httpx.HTTPError, ValueError, AttributeError):
            return False
        wanted = self._model if ":" in self._model else f"{self._model}:latest"
        return any(m.get("name") == wanted and not m.get("size_vram") for m in loaded)

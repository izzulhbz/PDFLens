"""Embeddings from a local Ollama server (POST /api/embed)."""

import logging
from collections.abc import Sequence
from typing import Any

import httpx

from app.embeddings.base import EmbeddingError
from app.models import EMBEDDING_DIM

logger = logging.getLogger(__name__)

UNREACHABLE_MESSAGE = (
    "The embedding service (Ollama) couldn't be reached. Check that it's running, "
    "then upload the file again."
)
MODEL_MISSING_MESSAGE = (
    "The embedding model isn't downloaded in Ollama. Run scripts/pull_models.sh, "
    "then upload the file again."
)

# nomic-embed-text was trained with task prefixes and retrieves better when
# documents and questions are labelled the way it saw during training.
NOMIC_DOCUMENT_PREFIX = "search_document: "
NOMIC_QUERY_PREFIX = "search_query: "


class OllamaEmbedder:
    dimension = EMBEDDING_DIM

    def __init__(
        self,
        client: httpx.Client,
        model: str,
        *,
        timeout_seconds: float = 120.0,
        batch_size: int = 16,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout = timeout_seconds
        # Several chunks per request is much faster than one at a time, while
        # keeping each request small enough to finish well within the timeout.
        self._batch_size = batch_size
        uses_nomic_prefixes = model.split(":")[0] == "nomic-embed-text"
        self._document_prefix = NOMIC_DOCUMENT_PREFIX if uses_nomic_prefixes else ""
        self._query_prefix = NOMIC_QUERY_PREFIX if uses_nomic_prefixes else ""

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = [self._document_prefix + t for t in texts[start : start + self._batch_size]]
            vectors.extend(self._embed(batch))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed([self._query_prefix + text])[0]

    def _embed(self, inputs: list[str]) -> list[list[float]]:
        try:
            response = self._client.post(
                "/api/embed",
                json={"model": self._model, "input": inputs},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise EmbeddingError(
                f"Ollama request failed: {type(exc).__name__}", user_message=UNREACHABLE_MESSAGE
            ) from exc

        if response.status_code == 404:
            raise EmbeddingError(
                f"Ollama has no model {self._model!r}", user_message=MODEL_MISSING_MESSAGE
            )
        if response.status_code != 200:
            raise EmbeddingError(
                f"Ollama returned HTTP {response.status_code}", user_message=UNREACHABLE_MESSAGE
            )

        vectors = _parse_embeddings(response)
        if len(vectors) != len(inputs) or any(len(v) != self.dimension for v in vectors):
            # Inserting would fail anyway; this gives a far clearer error.
            raise EmbeddingError(
                f"Expected {len(inputs)} vectors of size {self.dimension} from {self._model!r}",
                user_message=UNREACHABLE_MESSAGE,
            )
        return vectors


def _parse_embeddings(response: httpx.Response) -> list[list[float]]:
    try:
        body: Any = response.json()
        embeddings = body["embeddings"]
        return [[float(x) for x in vector] for vector in embeddings]
    except (ValueError, KeyError, TypeError) as exc:
        raise EmbeddingError(
            "Ollama returned an unexpected response body", user_message=UNREACHABLE_MESSAGE
        ) from exc

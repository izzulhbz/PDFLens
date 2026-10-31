"""The Embedder interface: turns text into vectors.

Everything in the app depends on this interface, not on Ollama directly,
so the embedding provider can be swapped (or faked in tests) without
touching the ingestion or retrieval code.

It's a typing.Protocol rather than an abstract base class: any class with
these methods and attribute counts as an Embedder (structural typing), so
the fakes don't need to inherit from anything.

Documents and queries have separate methods because some models, including
nomic-embed-text, expect a different prefix for each. Mixing them up still
"works" but makes retrieval noticeably worse.
"""

from collections.abc import Sequence
from typing import Protocol


class EmbeddingError(Exception):
    """The embedding service failed, or returned something unusable."""

    def __init__(self, message: str, *, user_message: str) -> None:
        super().__init__(message)
        # Safe to show in the UI (no hostnames or internal details).
        self.user_message = user_message


class Embedder(Protocol):
    dimension: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed chunks of a document, in order."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed a user's question."""
        ...

"""A deterministic stand-in for a real embedding model.

Used by the tests and the evaluation harness's mock mode, so CI needs no
Ollama and no model download. It is never selectable through configuration:
its vectors mean nothing to a real model, so they must never be mixed into
a real database.

How it works (the "hashing trick"): each word is hashed to one of the 768
positions, and the counts are scaled to unit length. Texts that share words
get similar vectors, so cosine-similarity search still finds the chunk that
talks about the same things as the question. It's a crude bag of words: no
synonyms and no word order.

The hash is blake2b, not Python's built-in hash(), because hash() of a
string changes every time Python starts (hash randomisation), and the same
text must always give the same vector.
"""

import hashlib
import math
import re
from collections.abc import Sequence

from app.models import EMBEDDING_DIM

_WORD = re.compile(r"[a-z0-9]+")

# Words so common they would make every text look alike.
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "does",
        "did",
        "for",
        "from",
        "has",
        "have",
        "how",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "this",
        "these",
        "those",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
    ]
)


class FakeEmbedder:
    dimension = EMBEDDING_DIM

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for word in _WORD.findall(text.lower()):
            if word in _STOPWORDS:
                continue
            digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
            position = int.from_bytes(digest[:4], "big") % self.dimension
            # A pseudo-random sign stops unrelated words that land on the same
            # position from always adding up.
            vector[position] += 1.0 if digest[4] % 2 else -1.0

        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            # Cosine distance is undefined for an all-zero vector, so text
            # with no content words gets a fixed unit vector instead.
            vector[0] = 1.0
            return vector
        return [v / norm for v in vector]

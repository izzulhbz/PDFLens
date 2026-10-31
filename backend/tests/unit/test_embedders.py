import json
import math
from typing import Any

import httpx
import pytest

from app.embeddings.base import EmbeddingError
from app.embeddings.fake import FakeEmbedder
from app.embeddings.ollama import MODEL_MISSING_MESSAGE, UNREACHABLE_MESSAGE, OllamaEmbedder
from app.models import EMBEDDING_DIM


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))  # inputs are unit vectors


# --- FakeEmbedder ------------------------------------------------------------------------


def test_fake_vectors_have_the_schema_dimension_and_unit_length():
    vector = FakeEmbedder().embed_query("pgvector stores embeddings")

    assert len(vector) == EMBEDDING_DIM
    assert math.sqrt(sum(v * v for v in vector)) == pytest.approx(1.0)


def test_fake_is_deterministic_across_instances():
    assert FakeEmbedder().embed_query("same text") == FakeEmbedder().embed_query("same text")


def test_fake_puts_related_text_closer_than_unrelated_text():
    embedder = FakeEmbedder()
    chunk = embedder.embed_documents(["HNSW is a graph index for nearest neighbour search."])[0]

    related = embedder.embed_query("What kind of index is HNSW?")
    unrelated = embedder.embed_query("When was the course founded?")

    assert cosine(chunk, related) > cosine(chunk, unrelated)


def test_fake_gives_a_valid_vector_for_text_without_content_words():
    vector = FakeEmbedder().embed_query("the of and")

    assert math.sqrt(sum(v * v for v in vector)) == pytest.approx(1.0)


# --- OllamaEmbedder (against a mocked Ollama API) -------------------------------------


class FakeOllama:
    """Records requests to /api/embed and answers with vectors of the right size."""

    def __init__(self, status: int = 200, dimension: int = EMBEDDING_DIM) -> None:
        self.requests: list[dict[str, Any]] = []
        self.status = status
        self.dimension = dimension

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "nope"})
        vectors = [[0.1] * self.dimension for _ in body["input"]]
        return httpx.Response(200, json={"embeddings": vectors})

    def client(self) -> httpx.Client:
        return httpx.Client(
            base_url="http://ollama.test", transport=httpx.MockTransport(self.handler)
        )


def test_documents_and_queries_get_nomic_task_prefixes():
    ollama = FakeOllama()
    embedder = OllamaEmbedder(ollama.client(), "nomic-embed-text")

    embedder.embed_documents(["chunk text"])
    embedder.embed_query("a question")

    assert ollama.requests[0]["input"] == ["search_document: chunk text"]
    assert ollama.requests[1]["input"] == ["search_query: a question"]
    assert ollama.requests[0]["model"] == "nomic-embed-text"


def test_other_models_get_no_prefix():
    ollama = FakeOllama()

    OllamaEmbedder(ollama.client(), "other-model").embed_query("a question")

    assert ollama.requests[0]["input"] == ["a question"]


def test_documents_are_embedded_in_batches_and_order_is_kept():
    ollama = FakeOllama()
    embedder = OllamaEmbedder(ollama.client(), "nomic-embed-text", batch_size=16)

    vectors = embedder.embed_documents([f"chunk {i}" for i in range(20)])

    assert [len(r["input"]) for r in ollama.requests] == [16, 4]
    assert ollama.requests[1]["input"][0] == "search_document: chunk 16"
    assert len(vectors) == 20


@pytest.mark.parametrize(
    ("status", "user_message"), [(404, MODEL_MISSING_MESSAGE), (500, UNREACHABLE_MESSAGE)]
)
def test_http_errors_become_embedding_errors(status, user_message):
    embedder = OllamaEmbedder(FakeOllama(status=status).client(), "nomic-embed-text")

    with pytest.raises(EmbeddingError) as raised:
        embedder.embed_query("q")

    assert raised.value.user_message == user_message


def test_wrong_dimension_is_an_embedding_error():
    embedder = OllamaEmbedder(FakeOllama(dimension=384).client(), "nomic-embed-text")

    with pytest.raises(EmbeddingError, match="size 768"):
        embedder.embed_query("q")


def test_connection_failure_is_an_embedding_error():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = httpx.Client(base_url="http://ollama.test", transport=httpx.MockTransport(refuse))

    with pytest.raises(EmbeddingError) as raised:
        OllamaEmbedder(client, "nomic-embed-text").embed_query("q")

    assert raised.value.user_message == UNREACHABLE_MESSAGE


def test_unexpected_response_body_is_an_embedding_error():
    client = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not json")),
    )

    with pytest.raises(EmbeddingError):
        OllamaEmbedder(client, "nomic-embed-text").embed_query("q")

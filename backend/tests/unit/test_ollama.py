import pytest

from app.ollama import has_model, list_models
from tests.conftest import fake_ollama


@pytest.mark.parametrize(
    ("wanted", "available", "expected"),
    [
        # An untagged name means ":latest".
        ("nomic-embed-text", {"nomic-embed-text:latest"}, True),
        ("llama3.2:1b", {"llama3.2:1b"}, True),
        # llama3.2 means the 3B ":latest" model; the 1B model doesn't count.
        ("llama3.2", {"llama3.2:1b"}, False),
        ("nomic-embed-text", set(), False),
    ],
)
def test_has_model(wanted, available, expected):
    assert has_model(wanted, available) is expected


def test_list_models_reads_names_from_api_tags():
    client = fake_ollama("nomic-embed-text:latest", "llama3.2:latest")

    assert list_models(client) == {"nomic-embed-text:latest", "llama3.2:latest"}

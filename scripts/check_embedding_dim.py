"""Embed one sentence with Ollama and check the vector size matches the schema.

The chunks.embedding column is vector(768). If the embedding model ever
returns a different size, every insert would fail, so this script confirms
the real number before we rely on it.

Usage (from the repository root, with the ollama container running and the
model pulled):
    backend/.venv/Scripts/python scripts/check_embedding_dim.py   # Windows
    backend/.venv/bin/python scripts/check_embedding_dim.py       # macOS/Linux
"""

import os
import sys

import httpx

EXPECTED_DIM = 768  # must match EMBEDDING_DIM in backend/app/models.py


def main() -> int:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11435")
    model = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    # /api/embed is Ollama's current embedding endpoint; it takes a list of
    # inputs and returns one vector per input.
    response = httpx.post(
        f"{base_url}/api/embed",
        json={"model": model, "input": ["search_document: PDFLens dimension check."]},
        timeout=120.0,  # the first call loads the model into memory, which is slow
    )
    response.raise_for_status()
    vector = response.json()["embeddings"][0]

    print(f"model={model} dimension={len(vector)} expected={EXPECTED_DIM}")
    if len(vector) != EXPECTED_DIM:
        print("MISMATCH: update EMBEDDING_DIM and add a migration before ingesting.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

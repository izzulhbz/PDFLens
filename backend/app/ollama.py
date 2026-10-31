"""Small helpers for talking to the Ollama HTTP API.

The app keeps one shared httpx.Client for Ollama (created in create_app),
which reuses connections between calls. Tests swap it for a client whose
transport is an httpx.MockTransport, so no real Ollama server is needed.
"""

import httpx


def list_models(client: httpx.Client) -> set[str]:
    """Return the names of the models pulled into Ollama, e.g. {"llama3.2:latest"}."""
    response = client.get("/api/tags")
    response.raise_for_status()
    return {model["name"] for model in response.json().get("models", [])}


def has_model(wanted: str, available: set[str]) -> bool:
    """True if `wanted` is pulled. A name with no tag means the ":latest" tag."""
    if ":" not in wanted:
        wanted = f"{wanted}:latest"
    return wanted in available

"""Reading the model choice sent with a question or summary request.

{"provider"?, "prefer"?}
- provider: anthropic, ollama_gpu, ollama or auto (the UI's "Default").
- prefer: the model auto mode tries first (the user's default model):
  anthropic, ollama_gpu or ollama. Ignored for any other provider.

Both are checked against allowlists and anything else is a 400, so a
client can't make the server call an arbitrary model or provider.
"""

from typing import Any

from app.errors import ApiError
from app.llm.base import PROVIDERS
from app.llm.router import MODELS


def read_provider_choice(data: dict[str, Any]) -> tuple[str | None, str | None]:
    """(provider, prefer) from a request body, or a 400."""
    provider = data.get("provider")
    if provider is not None and provider not in PROVIDERS:
        raise ApiError(400, "invalid_provider", f"provider must be one of {list(PROVIDERS)}.")
    prefer = data.get("prefer")
    if prefer is not None and prefer not in MODELS:
        raise ApiError(400, "invalid_provider", f"prefer must be one of {list(MODELS)}.")
    return provider, prefer

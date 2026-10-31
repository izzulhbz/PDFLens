#!/usr/bin/env bash
# Downloads the Ollama models PDFLens needs into the ollama container's volume.
# Run from the repository root while the stack is up:
#   docker compose up -d ollama
#   ./scripts/pull_models.sh
# Model names come from .env (OLLAMA_EMBED_MODEL, OLLAMA_CHAT_MODEL) when set.
set -euo pipefail

cd "$(dirname "$0")/.."

# Read only the two model names from .env, rather than sourcing the whole file.
read_env() {
  if [ -f .env ]; then
    grep -E "^$1=" .env | tail -n 1 | cut -d '=' -f 2- | tr -d '\r'
  fi
}

EMBED_MODEL="${OLLAMA_EMBED_MODEL:-$(read_env OLLAMA_EMBED_MODEL)}"
CHAT_MODEL="${OLLAMA_CHAT_MODEL:-$(read_env OLLAMA_CHAT_MODEL)}"
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"
CHAT_MODEL="${CHAT_MODEL:-llama3.2}"

for model in "$EMBED_MODEL" "$CHAT_MODEL"; do
  echo "Pulling ${model} ..."
  docker compose exec -T ollama ollama pull "${model}"
done

echo
docker compose exec -T ollama ollama list

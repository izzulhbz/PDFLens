"""Text embeddings. Embeddings always come from Ollama, whichever LLM answers
questions: vectors from different models live in different spaces and can't
be compared, so every chunk and every question must use the same model."""

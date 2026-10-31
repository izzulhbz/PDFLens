"""A fake LLM for tests and the evaluation harness's mock mode (no API key, no model).

It's "extractive": it reads the excerpts out of the prompt, picks the
sentence that shares the most words with the question, and returns that
sentence with a citation. If no sentence covers enough of the question's
words, it refuses, exactly as the real models are instructed to. Asked for
JSON (a document summary), it builds one from the first sentence of each
excerpt. That makes the whole pipeline (retrieval, prompt, citations,
refusals, summaries, audit log) testable end to end. It says nothing about
how good a real model's answers are; that is what running the evaluation
with --provider ollama or anthropic is for.

It ignores the system prompt, so it can't show whether prompt-injection
defences work on a real model either.
"""

import json
import re

from app.embeddings.fake import content_words
from app.llm.base import JsonSchema
from app.rag.prompt import REFUSAL, parse_user_prompt

# Share of the question's content words a sentence must contain to count
# as an answer.
MIN_QUESTION_COVERAGE = 0.5
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


class FakeLLM:
    name = "mock"

    def generate(self, system: str, user: str, *, json_schema: JsonSchema | None = None) -> str:
        question, excerpts = parse_user_prompt(user)
        if json_schema is not None:
            return _summary(excerpts)

        wanted = set(content_words(question))
        if not wanted:
            return REFUSAL

        best_score, best_answer = 0.0, REFUSAL
        for pages, text in excerpts:
            for sentence in _SENTENCE.split(text):
                score = len(wanted & set(content_words(sentence))) / len(wanted)
                if score > best_score:
                    citation = f"[p. {pages}]" if "-" not in pages else f"[pp. {pages}]"
                    best_score, best_answer = score, f"{sentence.strip()} {citation}"
        return best_answer if best_score >= MIN_QUESTION_COVERAGE else REFUSAL

    def availability(self) -> tuple[bool, str]:
        return True, "Fake model for tests"


def _summary(excerpts: list[tuple[str, str]]) -> str:
    """A summary in the expected JSON shape, built from the excerpts' first sentences."""
    topics = []
    for pages, text in excerpts[:5]:
        first_sentence = _SENTENCE.split(text.strip())[0]
        start, _, end = pages.partition("-")
        topics.append(
            {
                "name": " ".join(first_sentence.split()[:6]),
                "summary": first_sentence,
                "pages": list(range(int(start), int(end or start) + 1)),
            }
        )
    first = topics[0]["summary"] if topics else ""
    return json.dumps(
        {
            "title": first[:80],
            "overview": first,
            "topics": topics,
            "learning_outcomes": [f"Explain {t['name']}" for t in topics],
            "key_terms": [],
        }
    )

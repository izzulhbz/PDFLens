"""Splitting a document's text into overlapping chunks for retrieval.

Why chunk at all: a whole lecture won't fit in one embedding (and one vector
for 40 pages would blur every topic together), while single sentences lose
their context. Chunks of roughly 400-500 tokens are a common middle ground.

Why overlap: a fact that straddles a boundary would otherwise be cut in
half, with neither chunk containing all of it. Each chunk repeats the last
~50 tokens of the previous one.

Chunks may cross page boundaries, so each records the first and last page
its words came from (page_start, page_end), which become the citations.

Token counts are estimated, not measured: English text averages about 1.3
tokens per word in nomic-embed-text's (BERT-style) tokenizer. That's close
enough for sizing chunks and avoids adding a tokenizer library.
"""

from dataclasses import dataclass

from app.ingestion.pdf import PageText

TOKENS_PER_WORD = 1.3
# Chunks are at most 500 tokens, and end early (down to 80%, so 400 tokens)
# when that lets them finish at the end of a sentence: 400-500 tokens each.
CHUNK_TOKENS = 500
MIN_FILL_FOR_SENTENCE_END = 0.8
OVERLAP_TOKENS = 50
_SENTENCE_ENDINGS = (".", "?", "!", '."', '?"', '!"')


@dataclass(frozen=True)
class TextChunk:
    index: int
    page_start: int
    page_end: int
    text: str


def words_for_tokens(tokens: int) -> int:
    return round(tokens / TOKENS_PER_WORD)


def chunk_pages(
    pages: list[PageText],
    *,
    chunk_tokens: int = CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[TextChunk]:
    chunk_words = words_for_tokens(chunk_tokens)
    overlap_words = words_for_tokens(overlap_tokens)
    if not 0 <= overlap_words < chunk_words * MIN_FILL_FOR_SENTENCE_END:
        raise ValueError("Overlap must be smaller than the shortest possible chunk.")

    # Every word, tagged with the page it came from.
    words = [(word, page.page_number) for page in pages for word in page.text.split()]

    chunks: list[TextChunk] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_words, len(words))
        if end < len(words):
            end = _end_at_sentence(words, start, end, chunk_words)
        window = words[start:end]
        chunks.append(
            TextChunk(
                index=len(chunks),
                page_start=window[0][1],
                page_end=window[-1][1],
                text=" ".join(word for word, _ in window),
            )
        )
        if end == len(words):
            break
        # The next chunk starts `overlap_words` before this one ended.
        start = end - overlap_words
    return chunks


def _end_at_sentence(words: list[tuple[str, int]], start: int, end: int, chunk_words: int) -> int:
    """Move `end` back to just after the last sentence ending, if one is close enough."""
    earliest = start + int(chunk_words * MIN_FILL_FOR_SENTENCE_END)
    for i in range(end - 1, earliest - 1, -1):
        if words[i][0].endswith(_SENTENCE_ENDINGS):
            return i + 1
    return end

import itertools

import pytest

from app.ingestion.chunking import (
    CHUNK_TOKENS,
    MIN_FILL_FOR_SENTENCE_END,
    OVERLAP_TOKENS,
    TOKENS_PER_WORD,
    chunk_pages,
    words_for_tokens,
)
from app.ingestion.pdf import PageText
from tests.pdf_factory import words

CHUNK_WORDS = words_for_tokens(CHUNK_TOKENS)
OVERLAP_WORDS = words_for_tokens(OVERLAP_TOKENS)


def one_page(text: str) -> list[PageText]:
    return [PageText(1, text)]


def test_no_text_gives_no_chunks():
    assert chunk_pages([PageText(1, ""), PageText(2, "   ")]) == []


def test_short_document_is_one_chunk():
    [chunk] = chunk_pages(one_page("A short page about vectors."))

    assert (chunk.index, chunk.page_start, chunk.page_end) == (0, 1, 1)
    assert chunk.text == "A short page about vectors."


def test_consecutive_chunks_overlap_by_about_50_tokens():
    chunks = chunk_pages(one_page(words(1000)))

    for previous, current in itertools.pairwise(chunks):
        assert previous.text.split()[-OVERLAP_WORDS:] == current.text.split()[:OVERLAP_WORDS]
    assert pytest.approx(OVERLAP_TOKENS, abs=1) == OVERLAP_WORDS * TOKENS_PER_WORD


def test_chunks_are_400_to_500_estimated_tokens_except_the_last():
    chunks = chunk_pages(one_page(words(3000)))

    for chunk in chunks[:-1]:
        estimated_tokens = len(chunk.text.split()) * TOKENS_PER_WORD
        assert CHUNK_TOKENS * MIN_FILL_FOR_SENTENCE_END <= estimated_tokens <= CHUNK_TOKENS + 1


def test_every_word_is_covered_in_order():
    text = words(2000)
    chunks = chunk_pages(one_page(text))

    rebuilt = chunks[0].text.split()
    for chunk in chunks[1:]:
        rebuilt += chunk.text.split()[OVERLAP_WORDS:]
    assert rebuilt == text.split()


def test_chunk_indexes_are_sequential():
    chunks = chunk_pages(one_page(words(2000)))

    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_page_range_follows_the_words_across_page_boundaries():
    # 300 words per page: the first chunk (385 words) runs onto page 2.
    pages = [PageText(n, words(300, prefix=f"p{n}w")) for n in (1, 2, 3)]

    chunks = chunk_pages(pages)

    assert (chunks[0].page_start, chunks[0].page_end) == (1, 2)
    assert chunks[0].text.split()[0] == "p1w0"
    assert (chunks[-1].page_end) == 3
    for chunk in chunks:
        first_page = int(chunk.text.split()[0].split("w")[0][1:])
        last_page = int(chunk.text.split()[-1].split("w")[0][1:])
        assert (chunk.page_start, chunk.page_end) == (first_page, last_page)


def test_empty_pages_are_skipped_without_breaking_page_numbers():
    chunks = chunk_pages([PageText(1, ""), PageText(2, "Only page two has text.")])

    assert [(c.page_start, c.page_end) for c in chunks] == [(2, 2)]


def test_chunk_ends_at_a_sentence_boundary_when_one_is_near_the_end():
    sentence_end = CHUNK_WORDS - 20  # within the last 20% of the window
    tokens = words(1000).split()
    tokens[sentence_end - 1] += "."

    first = chunk_pages(one_page(" ".join(tokens)))[0]

    assert len(first.text.split()) == sentence_end
    assert first.text.endswith(".")


def test_sentence_end_too_early_in_the_window_is_ignored():
    tokens = words(1000).split()
    tokens[10] += "."  # far too early: ending here would make a tiny chunk

    first = chunk_pages(one_page(" ".join(tokens)))[0]

    assert len(first.text.split()) == CHUNK_WORDS


def test_overlap_must_be_smaller_than_a_chunk():
    with pytest.raises(ValueError, match="Overlap"):
        chunk_pages(one_page("x"), chunk_tokens=100, overlap_tokens=100)

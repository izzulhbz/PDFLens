"""Cleaning text extracted from PDFs before it is chunked and embedded.

Text from PDFs is messy in predictable ways, and the mess makes retrieval
worse: a header like "CS2103 Lecture 4" on every page would make every chunk
look similar, and "retriev-\nal" isn't the word "retrieval". The steps:

1. Unicode normalisation (NFKC): ligatures (the single character "fi") become "fi", and
   full-width and other look-alike characters become their plain form.
2. Invisible characters (soft hyphens, zero-width spaces) are removed, and
   other control characters become spaces.
3. Repeated headers and footers are dropped: a line near the top or bottom
   of a page that appears on at least half of the pages (with digits
   ignored, so "Page 3" and "Page 4" count as the same line).
4. Bare page numbers ("3", "Page 3", "3 / 12") at the top or bottom of a
   page are dropped.
5. Words broken across lines with a hyphen are rejoined ("retriev-" +
   "al" -> "retrieval"). This also joins a compound like "well-" + "known"
   into "wellknown"; that's rarer than hyphenation in lecture text, so it's
   an accepted trade-off.
6. All remaining whitespace collapses to single spaces.
"""

import re
import unicodedata
from collections import Counter

from app.ingestion.pdf import PageText

# Lines this close to the top or bottom of a page can be headers/footers.
EDGE_LINES = 2
# Header/footer detection only makes sense with a few pages to compare.
MIN_PAGES_FOR_BOILERPLATE = 3
BOILERPLATE_PAGE_FRACTION = 0.5

# Written as named escapes: the characters themselves are invisible in an editor.
_INVISIBLE = dict.fromkeys(
    map(
        ord,
        "\N{SOFT HYPHEN}\N{ZERO WIDTH SPACE}\N{ZERO WIDTH NON-JOINER}"
        "\N{ZERO WIDTH JOINER}\N{WORD JOINER}\N{ZERO WIDTH NO-BREAK SPACE}",
    )
)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_DIGITS = re.compile(r"\d+")
_WHITESPACE = re.compile(r"\s+")
# Optional dashes, optional "page", a number, optional "/ 12" or "of 12".
_DASHES = r"\-\N{EN DASH}\N{EM DASH}"
_PAGE_NUMBER = re.compile(
    rf"[{_DASHES}\s]*(page\s*)?\d{{1,4}}(\s*(/|of)\s*\d{{1,4}})?[{_DASHES}\s]*", re.IGNORECASE
)


def clean_pages(pages: list[PageText]) -> list[PageText]:
    lines_per_page = [_split_lines(page.text) for page in pages]
    boilerplate = _find_repeated_edge_lines(lines_per_page)

    cleaned = []
    for page, lines in zip(pages, lines_per_page, strict=True):
        kept = [
            line
            for position, line in enumerate(lines)
            if not _is_edge(position, len(lines))
            or (_signature(line) not in boilerplate and not _PAGE_NUMBER.fullmatch(line))
        ]
        cleaned.append(PageText(page.page_number, _join_lines(kept)))
    return cleaned


def _split_lines(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text).translate(_INVISIBLE)
    text = _CONTROL_CHARS.sub(" ", text)
    return [line.strip() for line in text.splitlines() if line.strip()]


def _is_edge(position: int, line_count: int) -> bool:
    return position < EDGE_LINES or position >= line_count - EDGE_LINES


def _signature(line: str) -> str:
    """A line with digits masked, so "Page 3" and "Page 4" look the same."""
    return _DIGITS.sub("#", _WHITESPACE.sub(" ", line.lower()))


def _find_repeated_edge_lines(lines_per_page: list[list[str]]) -> set[str]:
    if len(lines_per_page) < MIN_PAGES_FOR_BOILERPLATE:
        return set()
    pages_containing: Counter[str] = Counter()
    for lines in lines_per_page:
        edge = {_signature(line) for i, line in enumerate(lines) if _is_edge(i, len(lines))}
        pages_containing.update(edge)
    threshold = len(lines_per_page) * BOILERPLATE_PAGE_FRACTION
    return {sig for sig, count in pages_containing.items() if count >= threshold}


def _join_lines(lines: list[str]) -> str:
    text = ""
    for line in lines:
        if text.endswith("-") and len(text) > 1 and text[-2].isalpha() and line[:1].islower():
            text = text[:-1] + line  # rejoin a hyphenated word
        else:
            text = f"{text} {line}" if text else line
    return _WHITESPACE.sub(" ", text).strip()

from app.ingestion.cleaning import clean_pages
from app.ingestion.pdf import PageText


def clean(*texts: str) -> list[str]:
    pages = [PageText(i + 1, text) for i, text in enumerate(texts)]
    return [page.text for page in clean_pages(pages)]


def test_ligatures_and_lookalike_characters_are_normalised():
    text = (
        "\N{LATIN SMALL LIGATURE FI}nite \N{LATIN SMALL LIGATURE FL}ow "
        "\N{FULLWIDTH LATIN CAPITAL LETTER A}\N{FULLWIDTH LATIN CAPITAL LETTER B}"
    )

    assert clean(text) == ["finite flow AB"]


def test_invisible_and_control_characters_are_removed():
    text = "re\N{SOFT HYPHEN}trieval zero\N{ZERO WIDTH SPACE}width bad\x00byte"

    assert clean(text) == ["retrieval zerowidth bad byte"]


def test_words_hyphenated_across_lines_are_rejoined():
    assert clean("retrieval-aug-\nmented generation") == ["retrieval-augmented generation"]


def test_hyphen_before_a_capitalised_line_is_kept():
    # "Part A-" then "B" isn't a broken word.
    assert clean("Part A-\nB") == ["Part A- B"]


def test_whitespace_collapses_to_single_spaces():
    assert clean("one   two\n\n\nthree\tfour  ") == ["one two three four"]


def test_repeated_headers_and_footers_are_removed():
    topics = [
        "Vectors are lists.",
        "Cosine compares angles.",
        "HNSW is a graph.",
        "Chunks overlap.",
    ]
    pages = [f"CS101 Lecture 3\n{topic}\nPage {n} of 4" for n, topic in enumerate(topics, 1)]

    assert clean(*pages) == topics


def test_headers_are_kept_when_there_are_too_few_pages_to_compare():
    cleaned = clean("CS101 Lecture 3\nIntro.", "CS101 Lecture 3\nOutro.")

    assert cleaned == ["CS101 Lecture 3 Intro.", "CS101 Lecture 3 Outro."]


def test_a_line_on_only_some_pages_is_kept():
    pages = ["Overview\nalpha", "beta", "gamma", "delta"]

    assert clean(*pages)[0] == "Overview alpha"


def test_bare_page_numbers_at_the_edges_are_removed_but_numbers_in_content_stay():
    page = "7\nThe answer is\n42\nas everyone knows\nin this course.\n- 7 -"

    assert clean(page) == ["The answer is 42 as everyone knows in this course."]


def test_empty_page_stays_empty():
    assert clean("", "text") == ["", "text"]

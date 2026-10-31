import pytest

from app.ingestion.pdf import MAX_PAGES, InvalidPdfError, extract_pages, validate_pdf
from tests.pdf_factory import make_pdf


def test_valid_pdf_returns_its_page_count():
    assert validate_pdf(make_pdf(["one", "two", "three"])) == 3


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"Just some text pretending to be a PDF", "isn't a PDF"),
        (b"\x89PNG\r\n\x1a\n not a pdf", "isn't a PDF"),
        (b"%PDF-1.7\nthis is not really a pdf body", "damaged"),
    ],
)
def test_files_that_arent_pdfs_are_rejected(data, message):
    with pytest.raises(InvalidPdfError, match=message):
        validate_pdf(data)


def test_signature_must_be_at_the_very_start():
    with pytest.raises(InvalidPdfError, match="isn't a PDF"):
        validate_pdf(b"<html>" + make_pdf(["hidden"]))


def test_password_protected_pdf_is_rejected():
    with pytest.raises(InvalidPdfError, match="password-protected"):
        validate_pdf(make_pdf(["secret"], password="hunter2-hunter2"))


def test_too_many_pages_is_rejected():
    with pytest.raises(InvalidPdfError, match=f"at most {MAX_PAGES} pages"):
        validate_pdf(make_pdf([""] * (MAX_PAGES + 1)))


def test_extract_pages_keeps_one_based_page_numbers(tmp_path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(make_pdf(["First page text.", "", "Third page text."]))

    pages = extract_pages(path)

    assert [p.page_number for p in pages] == [1, 2, 3]
    assert "First page text." in pages[0].text
    assert pages[1].text.strip() == ""
    assert "Third page text." in pages[2].text

"""Builds small PDFs for tests, with PyMuPDF, so no binary fixtures live in the repo."""

import pymupdf

TEXT_BOX = pymupdf.Rect(72, 60, 540, 740)


def make_pdf(
    pages: list[str],
    *,
    header: str | None = None,
    page_numbers: bool = False,
    password: str | None = None,
) -> bytes:
    """A PDF with one page per string. Optionally a header and page number on every page."""
    doc = pymupdf.open()
    for number, text in enumerate(pages, start=1):
        page = doc.new_page(width=612, height=792)
        if header:
            page.insert_text((72, 40), header, fontsize=9)
        if text and page.insert_textbox(TEXT_BOX, text, fontsize=10) < 0:
            raise ValueError(f"Text for page {number} doesn't fit on one page.")
        if page_numbers:
            page.insert_text((300, 770), f"Page {number} of {len(pages)}", fontsize=9)
    if password:
        aes_256 = pymupdf.PDF_ENCRYPT_AES_256  # type: ignore[attr-defined]
        return bytes(doc.tobytes(encryption=aes_256, user_pw=password, owner_pw=password))
    return bytes(doc.tobytes())


def words(count: int, prefix: str = "w") -> str:
    """'w0 w1 w2 ...': distinct words, so tests can see exactly where chunks split."""
    return " ".join(f"{prefix}{i}" for i in range(count))

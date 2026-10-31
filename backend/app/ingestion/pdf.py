"""Reading PDFs with PyMuPDF: validating uploads and extracting text per page.

Every PyMuPDF call goes through _PYMUPDF_LOCK. PyMuPDF puts the underlying
MuPDF library in single-threaded mode, so two threads using it at once
(gunicorn serves requests on 8 threads, and ingestion runs on another) can
corrupt memory or crash the process. The lock makes them take turns.

Parsing untrusted files is the riskiest thing this app does: MuPDF is
written in C, and a malicious PDF could exploit a bug in it. Mitigations
here are keeping PyMuPDF up to date, refusing files that aren't plausibly
PDFs, capping the size and page count, and running the container as an
unprivileged user. A stronger design would parse in a separate, sandboxed
process.
"""

import threading
from dataclasses import dataclass
from pathlib import Path

import pymupdf

PDF_SIGNATURE = b"%PDF-"
MAX_PAGES = 300

_PYMUPDF_LOCK = threading.Lock()


class InvalidPdfError(Exception):
    """The upload isn't a PDF we can process. The message is safe to show the user."""


@dataclass(frozen=True)
class PageText:
    page_number: int  # 1-based, as people count pages
    text: str


def validate_pdf(data: bytes) -> int:
    """Check that `data` is a readable, unencrypted PDF and return its page count."""
    # The file signature ("magic bytes"), not the filename or the
    # Content-Type header, both of which the client chooses freely.
    if not data.startswith(PDF_SIGNATURE):
        raise InvalidPdfError("This file isn't a PDF.")

    with _PYMUPDF_LOCK:
        try:
            with pymupdf.open(stream=data, filetype="pdf") as doc:
                needs_password = bool(doc.needs_pass)
                page_count = int(doc.page_count)
        except pymupdf.FileDataError:
            raise InvalidPdfError("This PDF is damaged and can't be read.") from None

    if needs_password:
        raise InvalidPdfError("This PDF is password-protected. Remove the password and try again.")
    if page_count == 0:
        raise InvalidPdfError("This PDF has no pages.")
    if page_count > MAX_PAGES:
        raise InvalidPdfError(f"PDFs can have at most {MAX_PAGES} pages.")
    return page_count


def extract_pages(path: Path) -> list[PageText]:
    """The raw text of every page, keeping page numbers."""
    with _PYMUPDF_LOCK, pymupdf.open(path) as doc:
        # sort=True reads text blocks top-to-bottom, left-to-right, which
        # gives a more natural reading order on slides and multi-column pages.
        return [
            PageText(page_number=index + 1, text=page.get_text("text", sort=True))
            for index, page in enumerate(doc)
        ]

"""Paragraph-based DOCX parsing with logical page grouping.

DOCX files have no fixed page boundaries like PDFs. This module
extracts all non-empty paragraphs and groups them into logical
"pages" of approximately ``PAGE_CHAR_LIMIT`` characters. This
produces meaningful page numbers for source citations.
"""

from pathlib import Path

from docx import Document
from docx.opc.exceptions import PackageNotFoundError

from app.ingestion.types import ExtractedPage

PAGE_CHAR_LIMIT = 3000


class DOCXExtractionError(Exception):
    """Raised when a DOCX cannot be opened or contains no text."""


def extract_docx_pages(file_path: Path) -> list[ExtractedPage]:
    """Extract paragraphs from a DOCX and group them into logical pages.

    Paragraphs are concatenated until the running character count
    crosses ``PAGE_CHAR_LIMIT``, at which point a new logical page
    begins. This keeps the page sizes compatible with the downstream
    chunker's 500-token window.
    """
    if not file_path.is_file():
        raise DOCXExtractionError("DOCX file does not exist")

    try:
        document = Document(str(file_path))
    except PackageNotFoundError as error:
        raise DOCXExtractionError("File is not a valid DOCX") from error
    except Exception as error:
        raise DOCXExtractionError("DOCX is corrupted or unreadable") from error

    paragraphs = [
        paragraph.text.strip()
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]
    if not paragraphs:
        raise DOCXExtractionError("DOCX contains no extractable text")

    pages: list[ExtractedPage] = []
    current_parts: list[str] = []
    current_length = 0
    page_number = 1

    for paragraph in paragraphs:
        current_parts.append(paragraph)
        current_length += len(paragraph)
        if current_length >= PAGE_CHAR_LIMIT:
            pages.append({
                "page_number": page_number,
                "text": "\n\n".join(current_parts),
            })
            page_number += 1
            current_parts = []
            current_length = 0

    # Flush remaining paragraphs
    if current_parts:
        pages.append({
            "page_number": page_number,
            "text": "\n\n".join(current_parts),
        })

    return pages

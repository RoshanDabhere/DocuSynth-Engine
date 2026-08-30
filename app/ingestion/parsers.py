"""Page-by-page PDF parsing using PyMuPDF."""

from pathlib import Path

import pymupdf

from app.ingestion.types import ExtractedPage


class PDFExtractionError(Exception):
    """Raised when a PDF cannot be safely opened or extracted."""


def extract_pdf_pages(file_path: Path) -> list[ExtractedPage]:
    """Extract text from every PDF page while preserving page numbers."""
    if not file_path.is_file():
        raise PDFExtractionError("PDF file does not exist")

    try:
        with pymupdf.open(file_path) as document:
            if document.needs_pass:
                raise PDFExtractionError("Password-protected PDFs are not supported")
            if document.page_count == 0:
                raise PDFExtractionError("PDF contains no pages")

            return [
                {
                    "page_number": page_index + 1,
                    "text": document.load_page(page_index).get_text("text").strip(),
                }
                for page_index in range(document.page_count)
            ]
    except PDFExtractionError:
        raise
    except (pymupdf.FileDataError, pymupdf.EmptyFileError, RuntimeError) as error:
        raise PDFExtractionError("PDF is corrupted or unreadable") from error

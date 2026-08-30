"""Document loading services."""

from pathlib import Path

from langchain_community.document_loaders import TextLoader

from app.ingestion.types import ExtractedPage


class TXTExtractionError(Exception):
    """Raised when a TXT file cannot be decoded or contains no text."""


def extract_txt_pages(file_path: Path) -> list[ExtractedPage]:
    """Load a TXT file and return the normalized one-page structure."""
    if not file_path.is_file():
        raise TXTExtractionError("TXT file does not exist")

    try:
        documents = TextLoader(
            file_path=file_path,
            encoding="utf-8",
            autodetect_encoding=True,
        ).load()
    except (OSError, RuntimeError, UnicodeError) as error:
        raise TXTExtractionError("TXT file could not be decoded") from error

    text = "\n".join(document.page_content for document in documents).strip()
    if not text:
        raise TXTExtractionError("TXT file is empty")
    return [{"page_number": 1, "text": text}]

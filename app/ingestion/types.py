"""Shared document-ingestion data structures."""

from typing import TypedDict


class ExtractedPage(TypedDict):
    """Normalized text and metadata for one document page."""

    page_number: int
    text: str


class DocumentChunk(TypedDict):
    """Text chunk and ownership/source metadata."""

    chunk_id: str
    document_id: int
    user_id: int
    page_number: int
    chunk_index: int
    text: str

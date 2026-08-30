"""Structure-preserving text cleaning for LangChain documents."""

import re
from collections.abc import Sequence
from typing import Any

from langchain_core.documents import BaseDocumentTransformer, Document

from app.ingestion.types import ExtractedPage

CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
HORIZONTAL_WHITESPACE = re.compile(r"[^\S\n]+")
EXCESS_BLANK_LINES = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Normalize noise without removing meaningful paragraph boundaries."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = CONTROL_CHARACTERS.sub("", normalized)
    lines = [HORIZONTAL_WHITESPACE.sub(" ", line).strip() for line in normalized.split("\n")]
    return EXCESS_BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


class TextCleaningTransformer(BaseDocumentTransformer):
    """Clean LangChain documents while retaining their IDs and metadata."""

    def transform_documents(
        self,
        documents: Sequence[Document],
        **kwargs: Any,
    ) -> Sequence[Document]:
        """Return cleaned copies of the supplied LangChain documents."""
        return [
            Document(
                id=document.id,
                page_content=clean_text(document.page_content),
                metadata=dict(document.metadata),
            )
            for document in documents
        ]


def clean_extracted_pages(pages: list[ExtractedPage]) -> list[ExtractedPage]:
    """Clean normalized extracted pages through the LangChain transformer."""
    documents = [
        Document(page_content=page["text"], metadata={"page_number": page["page_number"]})
        for page in pages
    ]
    cleaned_documents = TextCleaningTransformer().transform_documents(documents)
    return [
        {
            "page_number": int(document.metadata["page_number"]),
            "text": document.page_content,
        }
        for document in cleaned_documents
    ]

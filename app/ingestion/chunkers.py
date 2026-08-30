"""Token-aware document chunking with LangChain."""

from uuid import NAMESPACE_URL, uuid5

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import get_settings
from app.ingestion.types import DocumentChunk, ExtractedPage


def create_text_splitter() -> RecursiveCharacterTextSplitter:
    """Create the configured recursive, token-aware LangChain splitter."""
    settings = get_settings()
    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=settings.chunk_size_tokens,
        chunk_overlap=settings.chunk_overlap_tokens,
        separators=["\n\n", "\n", ". ", " ", ""],
        add_start_index=True,
    )


def chunk_pages(
    pages: list[ExtractedPage],
    document_id: int,
    user_id: int,
) -> list[DocumentChunk]:
    """Split cleaned pages and attach document, user, page, and chunk metadata."""
    documents = [
        Document(
            page_content=page["text"],
            metadata={"page_number": page["page_number"]},
        )
        for page in pages
        if page["text"]
    ]
    split_documents = create_text_splitter().split_documents(documents)

    chunks: list[DocumentChunk] = []
    for chunk_index, document in enumerate(split_documents):
        page_number = int(document.metadata["page_number"])
        chunk_id = str(
            uuid5(
                NAMESPACE_URL,
                f"docusynth:{user_id}:{document_id}:{page_number}:{chunk_index}",
            )
        )
        chunks.append(
            {
                "chunk_id": chunk_id,
                "document_id": document_id,
                "user_id": user_id,
                "page_number": page_number,
                "chunk_index": chunk_index,
                "text": document.page_content,
            }
        )
    return chunks

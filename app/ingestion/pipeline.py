"""LangGraph document-ingestion workflow."""

from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.database.connection import SessionLocal
from app.embeddings.embedding_service import embed_texts
from app.ingestion.chunkers import chunk_pages
from app.ingestion.cleaners import clean_extracted_pages
from app.ingestion.loaders import extract_txt_pages
from app.ingestion.parsers import extract_pdf_pages
from app.ingestion.types import DocumentChunk, ExtractedPage
from app.models.documents import Document
from app.vector_store.qdrant_store import delete_document_points, store_chunks


class IngestionState(TypedDict, total=False):
    """Data passed between ingestion graph nodes."""

    document_id: int
    user_id: int
    filename: str
    file_path: Path
    file_type: str
    pages: list[ExtractedPage]
    chunks: list[DocumentChunk]
    embeddings: list[list[float]]
    stored_count: int


def load_document(state: IngestionState) -> IngestionState:
    """Extract normalized pages using the uploaded file type."""
    if state["file_type"] == "pdf":
        pages = extract_pdf_pages(state["file_path"])
    elif state["file_type"] == "txt":
        pages = extract_txt_pages(state["file_path"])
    else:
        raise ValueError(f"Unsupported document type: {state['file_type']}")
    return {"pages": pages}


def clean_document(state: IngestionState) -> IngestionState:
    """Normalize extracted text while preserving page boundaries."""
    pages = clean_extracted_pages(state["pages"])
    if not any(page["text"] for page in pages):
        raise ValueError("Document contains no extractable text")
    return {"pages": pages}


def split_document(state: IngestionState) -> IngestionState:
    """Create chunks with ownership and source metadata."""
    chunks = chunk_pages(
        state["pages"],
        document_id=state["document_id"],
        user_id=state["user_id"],
    )
    if not chunks:
        raise ValueError("Document produced no text chunks")
    return {"chunks": chunks}


def embed_document(state: IngestionState) -> IngestionState:
    """Generate document embeddings in one GPU-aware batch."""
    return {"embeddings": embed_texts([chunk["text"] for chunk in state["chunks"]])}


def store_document(state: IngestionState) -> IngestionState:
    """Persist embeddings and metadata in Qdrant."""
    stored_count = store_chunks(
        state["chunks"],
        state["embeddings"],
        filename=state["filename"],
    )
    return {"stored_count": stored_count}


def build_ingestion_graph():
    """Compile the ordered document-processing graph."""
    graph = StateGraph(IngestionState)
    graph.add_node("load", load_document)
    graph.add_node("clean", clean_document)
    graph.add_node("split", split_document)
    graph.add_node("embed", embed_document)
    graph.add_node("store", store_document)
    graph.add_edge(START, "load")
    graph.add_edge("load", "clean")
    graph.add_edge("clean", "split")
    graph.add_edge("split", "embed")
    graph.add_edge("embed", "store")
    graph.add_edge("store", END)
    return graph.compile()


INGESTION_GRAPH = build_ingestion_graph()


def process_document(document_id: int) -> None:
    """Process one database document and persist its final status."""
    with SessionLocal() as database:
        document = database.get(Document, document_id)
        if document is None:
            return
        document.status = "processing"
        document.chunk_count = 0
        document.processed_at = None
        database.commit()

        settings = get_settings()
        initial_state: IngestionState = {
            "document_id": document.id,
            "user_id": document.user_id,
            "filename": document.original_filename,
            "file_path": settings.upload_directory.resolve() / document.stored_filename,
            "file_type": document.file_type,
        }
        try:
            result = INGESTION_GRAPH.invoke(initial_state)
            document.status = "ready"
            document.chunk_count = result["stored_count"]
            document.processed_at = datetime.now(timezone.utc)
            database.commit()
        except Exception:
            database.rollback()
            failed_document = database.get(Document, document_id)
            if failed_document is not None:
                failed_document.status = "failed"
                failed_document.chunk_count = 0
                failed_document.processed_at = None
                database.commit()
                try:
                    delete_document_points(failed_document.user_id, failed_document.id)
                except Exception:
                    pass

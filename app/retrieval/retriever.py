"""Semantic retrieval over authenticated users' document chunks."""

from typing import Sequence, TypedDict

from app.config import get_settings
from app.embeddings.embedding_service import embed_query
from app.vector_store.qdrant_store import search_points


class RetrievedChunk(TypedDict):
    """One relevant chunk and its trustworthy Qdrant metadata."""

    chunk_id: str
    score: float
    user_id: int
    document_id: int
    filename: str
    page_number: int
    chunk_index: int
    text: str


def retrieve_chunks(
    question: str,
    user_id: int,
    document_ids: Sequence[int] | None = None,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    """Embed a question and return the user's most similar document chunks."""
    normalized_question = question.strip()
    if not normalized_question:
        raise ValueError("Question cannot be empty")
    if user_id < 1:
        raise ValueError("user_id must be positive")

    limit = top_k if top_k is not None else get_settings().retrieval_top_k
    if not 1 <= limit <= 50:
        raise ValueError("top_k must be between 1 and 50")

    query_vector = embed_query(normalized_question)
    points = search_points(
        query_vector=query_vector,
        user_id=user_id,
        document_ids=document_ids,
        limit=limit,
    )

    results: list[RetrievedChunk] = []
    for point in points:
        payload = point.payload or {}
        results.append(
            {
                "chunk_id": str(point.id),
                "score": float(point.score),
                "user_id": int(payload["user_id"]),
                "document_id": int(payload["document_id"]),
                "filename": str(payload["filename"]),
                "page_number": int(payload["page_number"]),
                "chunk_index": int(payload["chunk_index"]),
                "text": str(payload["text"]),
            }
        )
    return results

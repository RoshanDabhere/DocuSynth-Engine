"""Qdrant collection and point operations for document chunks."""

from functools import lru_cache
from typing import Any, Sequence

from qdrant_client import QdrantClient, models

from app.config import get_settings
from app.ingestion.types import DocumentChunk


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    """Create and cache one Qdrant HTTP client per application process."""
    settings = get_settings()
    return QdrantClient(
        url=settings.qdrant_url,
        timeout=settings.qdrant_timeout_seconds,
    )


def ensure_collection(client: QdrantClient | None = None) -> None:
    """Create the cosine-similarity collection and filter indexes if absent."""
    settings = get_settings()
    qdrant = client or get_qdrant_client()
    if qdrant.collection_exists(settings.qdrant_collection):
        collection = qdrant.get_collection(settings.qdrant_collection)
        vectors = collection.config.params.vectors
        if not isinstance(vectors, models.VectorParams):
            raise RuntimeError("Qdrant collection must use one unnamed dense vector")
        if vectors.size != settings.embedding_dimension:
            raise RuntimeError(
                "Qdrant vector size does not match EMBEDDING_DIMENSION: "
                f"{vectors.size} != {settings.embedding_dimension}"
            )
        if vectors.distance != models.Distance.COSINE:
            raise RuntimeError("Qdrant collection must use cosine distance")
        return

    qdrant.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=models.VectorParams(
            size=settings.embedding_dimension,
            distance=models.Distance.COSINE,
        ),
    )
    for field_name in ("user_id", "document_id"):
        qdrant.create_payload_index(
            collection_name=settings.qdrant_collection,
            field_name=field_name,
            field_schema=models.PayloadSchemaType.INTEGER,
        )


def store_chunks(
    chunks: Sequence[DocumentChunk],
    embeddings: Sequence[Sequence[float]],
    filename: str,
    client: QdrantClient | None = None,
) -> int:
    """Upsert chunk vectors and their ownership/source metadata."""
    if len(chunks) != len(embeddings):
        raise ValueError("Every chunk must have exactly one embedding")
    if not chunks:
        return 0

    settings = get_settings()
    qdrant = client or get_qdrant_client()
    ensure_collection(qdrant)
    points: list[models.PointStruct] = []
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        if len(embedding) != settings.embedding_dimension:
            raise ValueError(
                f"Embedding for chunk {chunk['chunk_id']} has invalid dimension"
            )
        payload: dict[str, Any] = {
            "user_id": chunk["user_id"],
            "document_id": chunk["document_id"],
            "filename": filename,
            "page_number": chunk["page_number"],
            "chunk_index": chunk["chunk_index"],
            "text": chunk["text"],
        }
        points.append(
            models.PointStruct(
                id=chunk["chunk_id"],
                vector=list(embedding),
                payload=payload,
            )
        )

    qdrant.upsert(
        collection_name=settings.qdrant_collection,
        points=points,
        wait=True,
    )
    return len(points)


def user_filter(
    user_id: int,
    document_ids: Sequence[int] | None = None,
) -> models.Filter:
    """Build the mandatory ownership filter, optionally limited to documents."""
    conditions: list[models.Condition] = [
        models.FieldCondition(
            key="user_id",
            match=models.MatchValue(value=user_id),
        )
    ]
    if document_ids is not None:
        if not document_ids:
            raise ValueError("document_ids cannot be empty when provided")
        conditions.append(
            models.FieldCondition(
                key="document_id",
                match=models.MatchAny(any=list(document_ids)),
            )
        )
    return models.Filter(must=conditions)


def search_points(
    query_vector: Sequence[float],
    user_id: int,
    document_ids: Sequence[int] | None = None,
    limit: int = 5,
    client: QdrantClient | None = None,
) -> list[models.ScoredPoint]:
    """Search similar chunks with a mandatory ownership filter."""
    if limit < 1:
        raise ValueError("Search limit must be at least 1")

    settings = get_settings()
    if len(query_vector) != settings.embedding_dimension:
        raise ValueError("Query vector has an invalid dimension")
    qdrant = client or get_qdrant_client()
    ensure_collection(qdrant)
    return qdrant.query_points(
        collection_name=settings.qdrant_collection,
        query=list(query_vector),
        query_filter=user_filter(user_id, document_ids),
        with_payload=True,
        with_vectors=False,
        limit=limit,
    ).points


def delete_document_points(
    user_id: int,
    document_id: int,
    client: QdrantClient | None = None,
) -> None:
    """Delete one document's vectors without crossing user boundaries."""
    settings = get_settings()
    qdrant = client or get_qdrant_client()
    qdrant.delete(
        collection_name=settings.qdrant_collection,
        points_selector=models.FilterSelector(
            filter=user_filter(user_id, [document_id])
        ),
        wait=True,
    )

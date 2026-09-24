"""Chat API request and response schemas."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PositiveIdentifier = Annotated[int, Field(gt=0)]

ConfidenceLevel = Literal["high", "medium", "low", "none"]


class ChatQueryRequest(BaseModel):
    """A question scoped to one or more selected documents."""

    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=4000)
    selected_document_ids: list[PositiveIdentifier] = Field(min_length=1, max_length=50)
    conversation_id: PositiveIdentifier | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("selected_document_ids")
    @classmethod
    def require_unique_document_ids(cls, document_ids: list[int]) -> list[int]:
        """Reject duplicate selections before querying PostgreSQL or Qdrant."""
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("selected_document_ids must not contain duplicates")
        return document_ids


class ChatSource(BaseModel):
    """Source metadata copied from an authenticated retrieval result."""

    source_number: PositiveIdentifier
    document_id: PositiveIdentifier
    filename: str
    page_number: PositiveIdentifier
    chunk_index: int = Field(ge=0)
    score: float
    text: str


class ChatQueryResponse(BaseModel):
    """A grounded answer and its retrieval-backed sources."""

    answer: str
    sources: list[ChatSource]
    conversation_id: PositiveIdentifier | None
    confidence: ConfidenceLevel

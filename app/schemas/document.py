"""Document API schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    """Safe uploaded-document metadata returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    file_type: str
    file_size: int
    status: str
    chunk_count: int
    created_at: datetime
    processed_at: datetime | None

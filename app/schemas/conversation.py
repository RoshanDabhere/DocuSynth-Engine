"""Conversation-history API response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MessageResponse(BaseModel):
    """One persisted user or assistant message."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    role: str
    content: str
    created_at: datetime


class ConversationResponse(BaseModel):
    """Conversation summary returned by history-list APIs."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(ConversationResponse):
    """Conversation summary together with its ordered messages."""

    messages: list[MessageResponse]

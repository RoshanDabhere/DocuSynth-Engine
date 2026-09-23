"""Authenticated document question-answering endpoints."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, DatabaseSession
from app.chains.conversational_rag import load_conversation_memory
from app.chains.rag_chain import run_rag, stream_rag
from app.database.connection import SessionLocal
from app.generation.llm_service import LLMServiceError
from app.models.conversation import Conversation
from app.models.documents import Document
from app.models.message import Message
from app.schemas.chat import ChatQueryRequest, ChatQueryResponse
from app.schemas.conversation import ConversationDetailResponse, ConversationResponse

router = APIRouter(prefix="/chat", tags=["Chat"])
CONVERSATION_TITLE_LENGTH = 80


def build_conversation_title(question: str) -> str:
    """Create a compact deterministic title from the first user question."""
    normalized = " ".join(question.split())
    if len(normalized) <= CONVERSATION_TITLE_LENGTH:
        return normalized
    return f"{normalized[: CONVERSATION_TITLE_LENGTH - 3].rstrip()}..."


def get_owned_conversation(
    conversation_id: int,
    user_id: int,
    database: DatabaseSession,
    *,
    include_messages: bool = False,
) -> Conversation:
    """Return a conversation only when it belongs to the authenticated user."""
    statement = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == user_id,
    )
    if include_messages:
        statement = statement.options(selectinload(Conversation.messages))
    conversation = database.scalar(statement)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return conversation


def resolve_conversation(
    conversation_id: int | None,
    user_id: int,
    question: str,
    database: DatabaseSession,
) -> Conversation:
    """Return an owned conversation or stage a new one for the first question."""
    if conversation_id is not None:
        return get_owned_conversation(conversation_id, user_id, database)
    conversation = Conversation(
        user_id=user_id,
        title=build_conversation_title(question),
    )
    database.add(conversation)
    return conversation


def save_messages(
    conversation: Conversation,
    messages: list[tuple[str, str]],
    database: DatabaseSession,
) -> None:
    """Persist ordered messages and update the conversation activity timestamp."""
    for role, content in messages:
        conversation.messages.append(Message(role=role, content=content))
    conversation.updated_at = datetime.now(timezone.utc)
    try:
        database.commit()
        database.refresh(conversation)
    except Exception:
        database.rollback()
        raise


@router.get("/conversations", response_model=list[ConversationResponse])
def list_conversations(
    current_user: CurrentUser,
    database: DatabaseSession,
) -> list[Conversation]:
    """List the authenticated user's conversations by recent activity."""
    return list(
        database.scalars(
            select(Conversation)
            .where(Conversation.user_id == current_user.id)
            .order_by(Conversation.updated_at.desc())
        )
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
)
def read_conversation(
    conversation_id: int,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> Conversation:
    """Return one owned conversation and its ordered message history."""
    return get_owned_conversation(
        conversation_id,
        current_user.id,
        database,
        include_messages=True,
    )


def verify_selected_documents(
    document_ids: list[int],
    user_id: int,
    database: DatabaseSession,
) -> None:
    """Require every selected document to belong to the user and be ready."""
    documents = list(
        database.scalars(
            select(Document).where(
                Document.user_id == user_id,
                Document.id.in_(document_ids),
            )
        )
    )
    owned_document_ids = {document.id for document in documents}
    if owned_document_ids != set(document_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more selected documents were not found",
        )
    if any(document.status != "ready" for document in documents):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="One or more selected documents are not ready for questions",
        )


@router.post("/query", response_model=ChatQueryResponse)
def query_documents(
    data: ChatQueryRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> ChatQueryResponse:
    """Answer a question using only the authenticated user's selected documents."""
    verify_selected_documents(data.selected_document_ids, current_user.id, database)
    conversation = resolve_conversation(
        data.conversation_id,
        current_user.id,
        data.question,
        database,
    )
    conversation_history = load_conversation_memory(
        conversation.id,
        current_user.id,
        database,
    )
    result = run_rag(
        question=data.question,
        user_id=current_user.id,
        document_ids=data.selected_document_ids,
        conversation_history=conversation_history,
    )
    save_messages(
        conversation,
        [("user", data.question), ("assistant", result["answer"])],
        database,
    )
    return ChatQueryResponse(
        answer=result["answer"],
        sources=result["sources"],
        conversation_id=conversation.id,
    )


def encode_sse(event_type: str, data: dict[str, object]) -> str:
    """Serialize one named Server-Sent Event with JSON data."""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/query/stream", response_class=StreamingResponse)
def stream_query_documents(
    data: ChatQueryRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> StreamingResponse:
    """Stream retrieval metadata and answer fragments using Server-Sent Events."""
    verify_selected_documents(data.selected_document_ids, current_user.id, database)
    conversation = resolve_conversation(
        data.conversation_id,
        current_user.id,
        data.question,
        database,
    )
    conversation_history = load_conversation_memory(
        conversation.id,
        current_user.id,
        database,
    )
    save_messages(conversation, [("user", data.question)], database)
    conversation_id = conversation.id

    def event_stream():
        answer_parts: list[str] = []
        try:
            for event in stream_rag(
                question=data.question,
                user_id=current_user.id,
                document_ids=data.selected_document_ids,
                conversation_history=conversation_history,
            ):
                event_type = event["type"]
                if event_type == "sources":
                    yield encode_sse("sources", {"sources": event["sources"]})
                elif event_type == "token":
                    answer_parts.append(event["token"])
                    yield encode_sse("token", {"token": event["token"]})
                else:
                    with SessionLocal() as history_database:
                        stored_conversation = get_owned_conversation(
                            conversation_id,
                            current_user.id,
                            history_database,
                        )
                        save_messages(
                            stored_conversation,
                            [("assistant", "".join(answer_parts))],
                            history_database,
                        )
                    yield encode_sse(
                        "done",
                        {"conversation_id": conversation_id},
                    )
        except LLMServiceError:
            yield encode_sse(
                "error",
                {"detail": "The language model is currently unavailable"},
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

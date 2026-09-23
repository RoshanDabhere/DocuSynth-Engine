"""Bounded conversation memory for follow-up document questions."""

from collections.abc import Sequence
from functools import lru_cache
from typing import Literal, TypedDict

import tiktoken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.conversation import Conversation
from app.models.message import Message

ROLE_TOKEN_OVERHEAD = 4
TRUNCATION_MARKER = " … [truncated]"


class ConversationMemoryMessage(TypedDict):
    """A role-labelled message safe to pass into the RAG prompt builder."""

    role: Literal["user", "assistant"]
    content: str


@lru_cache(maxsize=1)
def get_memory_tokenizer():
    """Return a cached tokenizer used to estimate the conversation budget."""
    return tiktoken.get_encoding("cl100k_base")


def count_memory_tokens(text: str) -> int:
    """Estimate prompt tokens with a stable local tokenizer."""
    return len(get_memory_tokenizer().encode(text))


def truncate_message_content(content: str, token_budget: int) -> str:
    """Fit one message into a token budget and mark content that was shortened."""
    if token_budget <= 0:
        return ""

    tokenizer = get_memory_tokenizer()
    content_tokens = tokenizer.encode(content)
    if len(content_tokens) <= token_budget:
        return content

    marker_tokens = tokenizer.encode(TRUNCATION_MARKER)
    if token_budget <= len(marker_tokens):
        return tokenizer.decode(content_tokens[:token_budget])
    kept_tokens = content_tokens[: token_budget - len(marker_tokens)]
    return f"{tokenizer.decode(kept_tokens).rstrip()}{TRUNCATION_MARKER}"


def trim_conversation_history(
    messages: Sequence[Message],
    *,
    max_messages: int,
    max_tokens: int,
) -> list[ConversationMemoryMessage]:
    """Keep the newest messages within both count and approximate token limits."""
    if max_messages < 1 or max_tokens < 1:
        return []

    selected_reversed: list[ConversationMemoryMessage] = []
    used_tokens = 0
    for message in reversed(messages[-max_messages:]):
        normalized_content = message.content.strip()
        if not normalized_content:
            continue

        remaining_tokens = max_tokens - used_tokens - ROLE_TOKEN_OVERHEAD
        if remaining_tokens <= 0:
            break
        fitted_content = truncate_message_content(
            normalized_content,
            remaining_tokens,
        )
        if not fitted_content:
            break

        selected_reversed.append(
            {"role": message.role, "content": fitted_content}
        )
        used_tokens += ROLE_TOKEN_OVERHEAD + count_memory_tokens(fitted_content)
        if fitted_content != normalized_content:
            break

    return list(reversed(selected_reversed))


def load_conversation_memory(
    conversation_id: int | None,
    user_id: int,
    database: Session,
) -> list[ConversationMemoryMessage]:
    """Load only the owned conversation's recent messages within configured limits."""
    if conversation_id is None:
        return []

    settings = get_settings()
    recent_messages = list(
        database.scalars(
            select(Message)
            .join(Conversation)
            .where(
                Message.conversation_id == conversation_id,
                Conversation.user_id == user_id,
            )
            .order_by(Message.id.desc())
            .limit(settings.conversation_memory_max_messages)
        )
    )
    return trim_conversation_history(
        list(reversed(recent_messages)),
        max_messages=settings.conversation_memory_max_messages,
        max_tokens=settings.conversation_memory_max_tokens,
    )

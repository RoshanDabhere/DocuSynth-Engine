"""Tests for bounded Phase 26 conversation memory."""

from types import SimpleNamespace
from unittest import TestCase

from app.chains.conversational_rag import (
    TRUNCATION_MARKER,
    count_memory_tokens,
    trim_conversation_history,
)
from app.generation.prompt_builder import build_rag_prompt


class ConversationMemoryTests(TestCase):
    """Verify recency, token limits, and prompt separation from evidence."""

    def test_window_keeps_only_the_newest_messages_in_order(self) -> None:
        messages = [
            SimpleNamespace(role="user", content="old question"),
            SimpleNamespace(role="assistant", content="old answer"),
            SimpleNamespace(role="user", content="recent question"),
            SimpleNamespace(role="assistant", content="recent answer"),
        ]

        memory = trim_conversation_history(
            messages,
            max_messages=2,
            max_tokens=100,
        )

        self.assertEqual(
            memory,
            [
                {"role": "user", "content": "recent question"},
                {"role": "assistant", "content": "recent answer"},
            ],
        )

    def test_oversized_boundary_message_is_marked_as_truncated(self) -> None:
        messages = [
            SimpleNamespace(role="assistant", content="context " * 100),
        ]

        memory = trim_conversation_history(
            messages,
            max_messages=8,
            max_tokens=20,
        )

        self.assertEqual(len(memory), 1)
        self.assertTrue(memory[0]["content"].endswith(TRUNCATION_MARKER))
        self.assertLessEqual(count_memory_tokens(memory[0]["content"]) + 4, 20)

    def test_prompt_labels_history_as_memory_not_document_evidence(self) -> None:
        chunk = {
            "chunk_id": "chunk-1",
            "score": 0.9,
            "user_id": 7,
            "document_id": 11,
            "filename": "notes.txt",
            "page_number": 1,
            "chunk_index": 0,
            "text": "Mira founded the project in Jaipur.",
        }

        prompt = build_rag_prompt(
            "Where did she found it?",
            [chunk],
            [
                {"role": "user", "content": "Who founded the project?"},
                {"role": "assistant", "content": "Mira [Source 1]"},
            ],
        )

        self.assertIn("CONVERSATION HISTORY", prompt.user)
        self.assertIn("ASSISTANT: Mira [Source 1]", prompt.user)
        self.assertIn("DOCUMENT CONTEXT", prompt.user)
        self.assertIn("CURRENT QUESTION\nWhere did she found it?", prompt.user)
        self.assertIn("history is not document evidence", prompt.system.lower())


if __name__ == "__main__":
    import unittest

    unittest.main()

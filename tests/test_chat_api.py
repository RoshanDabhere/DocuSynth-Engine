"""Focused tests for the Phase 23 and 24 chat endpoints."""

import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routes.chat import encode_sse, query_documents, verify_selected_documents
from app.chains.rag_chain import NO_CONTEXT_ANSWER, stream_rag
from app.main import app
from app.schemas.chat import ChatQueryRequest


class FakeDatabase:
    """Minimal SQLAlchemy session substitute for ownership checks."""

    def __init__(self, documents: list[SimpleNamespace]) -> None:
        self.documents = documents

    def scalars(self, _statement: object) -> list[SimpleNamespace]:
        """Return the documents prepared by a test."""
        return self.documents


class ChatApiTests(TestCase):
    """Verify request validation, ownership boundaries, and RAG delegation."""

    def test_chat_router_is_registered(self) -> None:
        paths = set(app.openapi()["paths"])
        self.assertIn("/chat/query", paths)

    def test_duplicate_document_ids_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ChatQueryRequest(
                question="What is this document about?",
                selected_document_ids=[11, 11],
            )

    def test_missing_or_unowned_document_is_hidden_as_not_found(self) -> None:
        database = FakeDatabase(
            [SimpleNamespace(id=11, status="ready")]
        )

        with self.assertRaises(HTTPException) as raised:
            verify_selected_documents([11, 99], user_id=7, database=database)

        self.assertEqual(raised.exception.status_code, 404)

    def test_document_must_be_ready(self) -> None:
        database = FakeDatabase(
            [SimpleNamespace(id=11, status="processing")]
        )

        with self.assertRaises(HTTPException) as raised:
            verify_selected_documents([11], user_id=7, database=database)

        self.assertEqual(raised.exception.status_code, 409)

    def test_query_uses_authenticated_user_and_selected_documents(self) -> None:
        database = FakeDatabase(
            [SimpleNamespace(id=11, status="ready")]
        )
        request = ChatQueryRequest(
            question="What is the main idea?",
            selected_document_ids=[11],
        )
        rag_result = {
            "answer": "The main idea is retrieval-grounded answering.",
            "sources": [
                {
                    "source_number": 1,
                    "document_id": 11,
                    "filename": "notes.pdf",
                    "page_number": 2,
                    "chunk_index": 0,
                    "score": 0.91,
                }
            ],
        }

        conversation = SimpleNamespace(id=23)
        with (
            patch("app.api.routes.chat.run_rag", return_value=rag_result) as run_rag_mock,
            patch(
                "app.api.routes.chat.resolve_conversation",
                return_value=conversation,
            ) as resolve_conversation_mock,
            patch(
                "app.api.routes.chat.load_conversation_memory",
                return_value=[],
            ) as load_memory_mock,
            patch("app.api.routes.chat.save_messages") as save_messages_mock,
        ):
            response = query_documents(
                data=request,
                current_user=SimpleNamespace(id=7),
                database=database,
            )

        self.assertEqual(response.answer, rag_result["answer"])
        self.assertEqual(response.sources[0].document_id, 11)
        self.assertEqual(response.conversation_id, 23)
        run_rag_mock.assert_called_once_with(
            question="What is the main idea?",
            user_id=7,
            document_ids=[11],
            conversation_history=[],
        )
        resolve_conversation_mock.assert_called_once_with(
            None,
            7,
            "What is the main idea?",
            database,
        )
        load_memory_mock.assert_called_once_with(23, 7, database)
        save_messages_mock.assert_called_once_with(
            conversation,
            [
                ("user", "What is the main idea?"),
                ("assistant", rag_result["answer"]),
            ],
            database,
        )

    def test_conversation_history_routes_are_registered(self) -> None:
        paths = app.openapi()["paths"]
        self.assertIn("/chat/conversations", paths)
        self.assertIn("/chat/conversations/{conversation_id}", paths)

    def test_streaming_chat_router_is_registered(self) -> None:
        self.assertIn("/chat/query/stream", app.openapi()["paths"])

    def test_sse_payload_is_named_and_json_encoded(self) -> None:
        event = encode_sse("token", {"token": "first\nsecond"})
        event_lines = event.splitlines()
        self.assertEqual(event_lines[0], "event: token")
        self.assertEqual(
            json.loads(event_lines[1].removeprefix("data: ")),
            {"token": "first\nsecond"},
        )


class RAGStreamingTests(TestCase):
    """Verify that streaming uses provider fragments and trusted metadata."""

    def test_stream_rag_emits_sources_provider_tokens_and_done(self) -> None:
        chunk = {
            "chunk_id": "chunk-1",
            "score": 0.91,
            "user_id": 7,
            "document_id": 11,
            "filename": "notes.pdf",
            "page_number": 2,
            "chunk_index": 0,
            "text": "The launch code is ORBIT-742.",
        }
        provider = Mock()
        provider.stream_generate.return_value = iter(["ORBIT", "-742"])

        with (
            patch("app.chains.rag_chain.retrieve_chunks", return_value=[chunk]),
            patch("app.chains.rag_chain.get_llm_service", return_value=provider),
        ):
            events = list(
                stream_rag(
                    question="What is the launch code?",
                    user_id=7,
                    document_ids=[11],
                )
            )

        self.assertEqual(events[0]["type"], "sources")
        self.assertEqual(events[0]["sources"][0]["document_id"], 11)
        self.assertEqual(
            [event["token"] for event in events if event["type"] == "token"],
            ["ORBIT", "-742"],
        )
        self.assertEqual(events[-1], {"type": "done"})
        provider.stream_generate.assert_called_once()

    def test_no_context_stream_does_not_call_the_llm(self) -> None:
        provider_factory = Mock()
        with (
            patch("app.chains.rag_chain.retrieve_chunks", return_value=[]),
            patch("app.chains.rag_chain.get_llm_service", provider_factory),
        ):
            events = list(stream_rag(question="Unknown?", user_id=7, document_ids=[11]))

        self.assertEqual(events[0], {"type": "sources", "sources": []})
        self.assertEqual(events[1], {"type": "token", "token": NO_CONTEXT_ANSWER})
        self.assertEqual(events[2], {"type": "done"})
        provider_factory.assert_not_called()


if __name__ == "__main__":
    import unittest

    unittest.main()

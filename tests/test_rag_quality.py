"""Tests for Phase 30 RAG quality configuration and confidence scoring."""

from unittest import TestCase
from unittest.mock import Mock, patch

from pydantic import ValidationError

from app.chains.rag_chain import (
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    calculate_confidence,
    stream_rag,
)
from app.schemas.chat import ChatQueryRequest, ChatQueryResponse


class ConfidenceCalculationTests(TestCase):
    """Verify confidence banding logic against documented thresholds."""

    def _chunk(self, score: float) -> dict:
        return {
            "chunk_id": "c1",
            "score": score,
            "user_id": 7,
            "document_id": 11,
            "filename": "notes.txt",
            "page_number": 1,
            "chunk_index": 0,
            "text": "sample text",
        }

    def test_no_chunks_returns_none(self) -> None:
        self.assertEqual(calculate_confidence([]), "none")

    def test_high_confidence_when_average_above_threshold(self) -> None:
        chunks = [self._chunk(0.90), self._chunk(0.85), self._chunk(0.80)]
        self.assertEqual(calculate_confidence(chunks), "high")

    def test_medium_confidence_between_thresholds(self) -> None:
        chunks = [self._chunk(0.65), self._chunk(0.55), self._chunk(0.50)]
        self.assertEqual(calculate_confidence(chunks), "medium")

    def test_low_confidence_below_medium_threshold(self) -> None:
        chunks = [self._chunk(0.40), self._chunk(0.38), self._chunk(0.35)]
        self.assertEqual(calculate_confidence(chunks), "low")

    def test_single_high_chunk_is_high(self) -> None:
        """When there are fewer than 3 chunks, average only available scores."""
        self.assertEqual(calculate_confidence([self._chunk(0.92)]), "high")

    def test_boundary_at_high_threshold(self) -> None:
        chunks = [self._chunk(CONFIDENCE_HIGH_THRESHOLD)]
        self.assertEqual(calculate_confidence(chunks), "high")

    def test_boundary_just_below_high(self) -> None:
        chunks = [self._chunk(CONFIDENCE_HIGH_THRESHOLD - 0.01)]
        self.assertEqual(calculate_confidence(chunks), "medium")

    def test_boundary_at_medium_threshold(self) -> None:
        chunks = [self._chunk(CONFIDENCE_MEDIUM_THRESHOLD)]
        self.assertEqual(calculate_confidence(chunks), "medium")

    def test_boundary_just_below_medium(self) -> None:
        chunks = [self._chunk(CONFIDENCE_MEDIUM_THRESHOLD - 0.01)]
        self.assertEqual(calculate_confidence(chunks), "low")


class QualityRequestSchemaTests(TestCase):
    """Verify per-request quality parameter validation."""

    def test_valid_top_k_is_accepted(self) -> None:
        request = ChatQueryRequest(
            question="test",
            selected_document_ids=[1],
            top_k=10,
        )
        self.assertEqual(request.top_k, 10)

    def test_top_k_below_minimum_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ChatQueryRequest(question="test", selected_document_ids=[1], top_k=0)

    def test_top_k_above_maximum_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ChatQueryRequest(question="test", selected_document_ids=[1], top_k=21)

    def test_valid_score_threshold_is_accepted(self) -> None:
        request = ChatQueryRequest(
            question="test",
            selected_document_ids=[1],
            score_threshold=0.5,
        )
        self.assertAlmostEqual(request.score_threshold, 0.5)

    def test_negative_score_threshold_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ChatQueryRequest(
                question="test",
                selected_document_ids=[1],
                score_threshold=-0.1,
            )

    def test_score_threshold_above_one_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ChatQueryRequest(
                question="test",
                selected_document_ids=[1],
                score_threshold=1.1,
            )

    def test_omitted_quality_params_default_to_none(self) -> None:
        request = ChatQueryRequest(question="test", selected_document_ids=[1])
        self.assertIsNone(request.top_k)
        self.assertIsNone(request.score_threshold)


class QualityResponseSchemaTests(TestCase):
    """Verify confidence is required in the response schema."""

    def test_response_requires_confidence(self) -> None:
        with self.assertRaises(ValidationError):
            ChatQueryResponse(
                answer="test",
                sources=[],
                conversation_id=1,
                # confidence intentionally omitted
            )

    def test_response_accepts_valid_confidence(self) -> None:
        response = ChatQueryResponse(
            answer="test",
            sources=[],
            conversation_id=1,
            confidence="high",
        )
        self.assertEqual(response.confidence, "high")

    def test_invalid_confidence_level_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ChatQueryResponse(
                answer="test",
                sources=[],
                conversation_id=1,
                confidence="unknown",
            )


class StreamingConfidenceTests(TestCase):
    """Verify that stream_rag emits confidence in the sources event."""

    def test_sources_event_includes_confidence(self) -> None:
        chunk = {
            "chunk_id": "c1",
            "score": 0.88,
            "user_id": 7,
            "document_id": 11,
            "filename": "notes.txt",
            "page_number": 1,
            "chunk_index": 0,
            "text": "Important fact.",
        }
        provider = Mock()
        provider.stream_generate.return_value = iter(["Answer"])

        with (
            patch("app.chains.rag_chain.retrieve_chunks", return_value=[chunk]),
            patch("app.chains.rag_chain.get_llm_service", return_value=provider),
        ):
            events = list(
                stream_rag(question="test?", user_id=7, document_ids=[11])
            )

        sources_event = events[0]
        self.assertEqual(sources_event["type"], "sources")
        self.assertEqual(sources_event["confidence"], "high")

    def test_empty_retrieval_yields_none_confidence(self) -> None:
        with patch("app.chains.rag_chain.retrieve_chunks", return_value=[]):
            events = list(
                stream_rag(question="test?", user_id=7, document_ids=[11])
            )

        self.assertEqual(events[0]["confidence"], "none")


if __name__ == "__main__":
    import unittest

    unittest.main()

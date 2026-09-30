"""Tests for the Phase 32 health check endpoint and observability."""

from unittest import TestCase
from unittest.mock import patch, MagicMock

from app.api.routes.health import (
    HealthResponse,
    DependencyCheck,
    _check_database,
    _check_qdrant,
    _check_ollama,
    health_check,
)
from app.main import app


class HealthEndpointRegistrationTests(TestCase):
    """Verify the health route is properly registered."""

    def test_health_route_is_registered(self) -> None:
        paths = app.openapi()["paths"]
        self.assertIn("/health", paths)
        self.assertIn("get", paths["/health"])


class HealthStatusLogicTests(TestCase):
    """Verify the tri-state health status logic."""

    def _ok_check(self) -> DependencyCheck:
        return DependencyCheck(status="ok", latency_ms=1.0)

    def _error_check(self) -> DependencyCheck:
        return DependencyCheck(status="error", latency_ms=1.0, detail="down")

    @patch("app.api.routes.health._check_ollama")
    @patch("app.api.routes.health._check_qdrant")
    @patch("app.api.routes.health._check_database")
    def test_all_healthy(self, db_mock, qdrant_mock, ollama_mock) -> None:
        db_mock.return_value = self._ok_check()
        qdrant_mock.return_value = self._ok_check()
        ollama_mock.return_value = self._ok_check()
        result = health_check()
        self.assertEqual(result.status, "healthy")

    @patch("app.api.routes.health._check_ollama")
    @patch("app.api.routes.health._check_qdrant")
    @patch("app.api.routes.health._check_database")
    def test_ollama_down_is_degraded(self, db_mock, qdrant_mock, ollama_mock) -> None:
        db_mock.return_value = self._ok_check()
        qdrant_mock.return_value = self._ok_check()
        ollama_mock.return_value = self._error_check()
        result = health_check()
        self.assertEqual(result.status, "degraded")

    @patch("app.api.routes.health._check_ollama")
    @patch("app.api.routes.health._check_qdrant")
    @patch("app.api.routes.health._check_database")
    def test_database_down_is_unhealthy(self, db_mock, qdrant_mock, ollama_mock) -> None:
        db_mock.return_value = self._error_check()
        qdrant_mock.return_value = self._ok_check()
        ollama_mock.return_value = self._ok_check()
        result = health_check()
        self.assertEqual(result.status, "unhealthy")

    @patch("app.api.routes.health._check_ollama")
    @patch("app.api.routes.health._check_qdrant")
    @patch("app.api.routes.health._check_database")
    def test_qdrant_down_is_unhealthy(self, db_mock, qdrant_mock, ollama_mock) -> None:
        db_mock.return_value = self._ok_check()
        qdrant_mock.return_value = self._error_check()
        ollama_mock.return_value = self._ok_check()
        result = health_check()
        self.assertEqual(result.status, "unhealthy")

    @patch("app.api.routes.health._check_ollama")
    @patch("app.api.routes.health._check_qdrant")
    @patch("app.api.routes.health._check_database")
    def test_all_down_is_unhealthy(self, db_mock, qdrant_mock, ollama_mock) -> None:
        db_mock.return_value = self._error_check()
        qdrant_mock.return_value = self._error_check()
        ollama_mock.return_value = self._error_check()
        result = health_check()
        self.assertEqual(result.status, "unhealthy")

    @patch("app.api.routes.health._check_ollama")
    @patch("app.api.routes.health._check_qdrant")
    @patch("app.api.routes.health._check_database")
    def test_response_includes_all_three_checks(self, db_mock, qdrant_mock, ollama_mock) -> None:
        db_mock.return_value = self._ok_check()
        qdrant_mock.return_value = self._ok_check()
        ollama_mock.return_value = self._ok_check()
        result = health_check()
        self.assertIn("database", result.checks)
        self.assertIn("qdrant", result.checks)
        self.assertIn("ollama", result.checks)


class DependencyCheckSchemaTests(TestCase):
    """Verify the DependencyCheck schema."""

    def test_ok_check_without_detail(self) -> None:
        check = DependencyCheck(status="ok", latency_ms=2.3)
        self.assertEqual(check.status, "ok")
        self.assertIsNone(check.detail)

    def test_error_check_with_detail(self) -> None:
        check = DependencyCheck(status="error", latency_ms=5.0, detail="Connection refused")
        self.assertEqual(check.status, "error")
        self.assertEqual(check.detail, "Connection refused")


class DatabaseCheckTests(TestCase):
    """Verify the database health probe."""

    @patch("app.api.routes.health.SessionLocal")
    def test_database_ok_returns_ok_status(self, session_mock) -> None:
        mock_session = MagicMock()
        session_mock.return_value.__enter__ = MagicMock(return_value=mock_session)
        session_mock.return_value.__exit__ = MagicMock(return_value=False)
        result = _check_database()
        self.assertEqual(result.status, "ok")
        self.assertIsNotNone(result.latency_ms)

    @patch("app.api.routes.health.SessionLocal")
    def test_database_error_returns_error_status(self, session_mock) -> None:
        session_mock.return_value.__enter__ = MagicMock(
            side_effect=RuntimeError("Connection refused")
        )
        session_mock.return_value.__exit__ = MagicMock(return_value=False)
        result = _check_database()
        self.assertEqual(result.status, "error")
        self.assertIn("Connection refused", result.detail)


if __name__ == "__main__":
    import unittest

    unittest.main()

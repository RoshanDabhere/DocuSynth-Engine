"""Health check endpoint that probes all external dependencies."""

import logging
import time
from typing import Literal

import httpx
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.config import get_settings
from app.database.connection import SessionLocal

logger = logging.getLogger("app.api.routes.health")

router = APIRouter(tags=["Health"])

HealthStatus = Literal["healthy", "degraded", "unhealthy"]


class DependencyCheck(BaseModel):
    """Result of probing one external dependency."""

    status: Literal["ok", "error"]
    latency_ms: float | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    """Aggregate health report for all dependencies."""

    status: HealthStatus
    checks: dict[str, DependencyCheck]


def _check_database() -> DependencyCheck:
    """Probe PostgreSQL with a trivial query."""
    start = time.perf_counter()
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start) * 1000
        return DependencyCheck(status="ok", latency_ms=round(latency, 1))
    except Exception as error:
        latency = (time.perf_counter() - start) * 1000
        return DependencyCheck(
            status="error",
            latency_ms=round(latency, 1),
            detail=str(error)[:200],
        )


def _check_qdrant() -> DependencyCheck:
    """Probe Qdrant by listing collections."""
    settings = get_settings()
    start = time.perf_counter()
    try:
        response = httpx.get(
            f"{settings.qdrant_url}/collections",
            timeout=settings.qdrant_timeout_seconds,
        )
        response.raise_for_status()
        latency = (time.perf_counter() - start) * 1000
        return DependencyCheck(status="ok", latency_ms=round(latency, 1))
    except Exception as error:
        latency = (time.perf_counter() - start) * 1000
        return DependencyCheck(
            status="error",
            latency_ms=round(latency, 1),
            detail=str(error)[:200],
        )


def _check_ollama() -> DependencyCheck:
    """Probe Ollama by hitting the version endpoint."""
    settings = get_settings()
    start = time.perf_counter()
    try:
        response = httpx.get(
            f"{settings.ollama_url}/api/version",
            timeout=5.0,
        )
        response.raise_for_status()
        latency = (time.perf_counter() - start) * 1000
        return DependencyCheck(status="ok", latency_ms=round(latency, 1))
    except Exception as error:
        latency = (time.perf_counter() - start) * 1000
        return DependencyCheck(
            status="error",
            latency_ms=round(latency, 1),
            detail=str(error)[:200],
        )


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Probe PostgreSQL, Qdrant, and Ollama and return aggregate status.

    Status logic:
        healthy  — all dependencies respond normally
        degraded — Ollama is down (queries won't work but uploads can)
        unhealthy — database or Qdrant is down (nothing works)
    """
    checks = {
        "database": _check_database(),
        "qdrant": _check_qdrant(),
        "ollama": _check_ollama(),
    }

    critical_ok = all(
        checks[name].status == "ok" for name in ("database", "qdrant")
    )
    all_ok = all(check.status == "ok" for check in checks.values())

    if all_ok:
        status: HealthStatus = "healthy"
    elif critical_ok:
        status = "degraded"
    else:
        status = "unhealthy"

    logger.info(
        "Health check: %s (db=%s, qdrant=%s, ollama=%s)",
        status,
        checks["database"].status,
        checks["qdrant"].status,
        checks["ollama"].status,
    )
    return HealthResponse(status=status, checks=checks)

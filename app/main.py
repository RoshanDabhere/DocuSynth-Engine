"""FastAPI application entry point for DocuSynth Engine."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.documents import router as documents_router
from app.api.routes.health import router as health_router
from app.config import get_settings
from app.observability.logging import configure_logging
from app.observability.middleware import RequestIdMiddleware

logger = logging.getLogger("app.main")


def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""
    configure_logging()

    settings = get_settings()
    application = FastAPI(
        title="DocuSynth Engine API",
        description="Backend API for the Smart RAG document assistant.",
        version="0.1.0",
    )

    # ── Middleware (order matters: outermost wraps first) ──
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Server-Timing"],
    )

    # ── Global exception handler ──
    @application.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Catch any unhandled exception, log it, and return a safe 500."""
        logger.error(
            "Unhandled exception on %s %s: %s",
            request.method,
            request.url.path,
            exc,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected error occurred"},
        )

    # ── Routes ──
    @application.get("/", tags=["General"])
    async def read_root() -> dict[str, str]:
        """Return a small response confirming that the API is running."""
        return {
            "message": "DocuSynth Engine API is running",
            "docs_url": "/docs",
        }

    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(documents_router)
    application.include_router(chat_router)

    logger.info("DocuSynth Engine started (environment=%s)", settings.app_environment)
    return application


app = create_application()

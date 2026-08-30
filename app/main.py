"""FastAPI application entry point for DocuSynth Engine."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.documents import router as documents_router
from app.config import get_settings


def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    application = FastAPI(
        title="DocuSynth Engine API",
        description="Backend API for the Smart RAG document assistant.",
        version="0.1.0",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/", tags=["General"])
    async def read_root() -> dict[str, str]:
        """Return a small response confirming that the API is running."""
        return {
            "message": "DocuSynth Engine API is running",
            "docs_url": "/docs",
        }

    application.include_router(auth_router)
    application.include_router(documents_router)

    return application


app = create_application()

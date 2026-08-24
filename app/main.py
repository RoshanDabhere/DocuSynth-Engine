"""FastAPI application entry point for DocuSynth Engine."""

from fastapi import FastAPI


def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="DocuSynth Engine API",
        description="Backend API for the Smart RAG document assistant.",
        version="0.1.0",
    )

    @application.get("/", tags=["General"])
    async def read_root() -> dict[str, str]:
        """Return a small response confirming that the API is running."""
        return {
            "message": "DocuSynth Engine API is running",
            "docs_url": "/docs",
        }

    return application


app = create_application()

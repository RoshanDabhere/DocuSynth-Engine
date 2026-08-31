"""Environment-based application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from environment variables or a local .env file."""

    app_name: str = "DocuSynth Engine API"
    app_environment: str = "development"
    frontend_origin: str = "http://localhost:5500"
    database_url: SecretStr
    jwt_secret_key: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "document_chunks"
    qdrant_timeout_seconds: float = 10.0
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:4b"
    ollama_timeout_seconds: float = 120.0
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024
    llm_keep_alive: str = "10m"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_device: str = "auto"
    embedding_batch_size: int = 32
    embedding_dimension: int = 384
    retrieval_top_k: int = 5
    retrieval_score_threshold: float = 0.0
    upload_directory: Path = Path("uploads")
    max_upload_size_bytes: int = 10 * 1024 * 1024
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 75

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings instance for the application process."""
    return Settings()

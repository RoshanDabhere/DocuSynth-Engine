"""Environment-based application settings."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from environment variables or a local .env file."""

    app_name: str = "DocuSynth Engine API"
    app_environment: str = "development"
    database_url: SecretStr
    jwt_secret_key: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    qdrant_url: str = "http://localhost:6333"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:4b"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings instance for the application process."""
    return Settings()

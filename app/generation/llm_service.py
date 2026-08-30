"""Replaceable LLM interface and local Ollama implementation."""

from collections.abc import Iterator
from functools import lru_cache
from typing import Protocol

import httpx
from ollama import Client, ResponseError

from app.config import get_settings


class LLMServiceError(RuntimeError):
    """Raised when the configured language-model provider fails."""


class LLMProvider(Protocol):
    """Provider-neutral contract used by future RAG services."""

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generate one complete response."""
        ...

    def stream_generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> Iterator[str]:
        """Yield response text as it is generated."""
        ...


class OllamaLLM:
    """Local Ollama-backed implementation of the LLM contract."""

    def __init__(
        self,
        client: Client,
        model: str,
        temperature: float,
        max_tokens: int,
        keep_alive: str,
    ) -> None:
        self.client = client
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.keep_alive = keep_alive

    def _validate_prompt(self, prompt: str) -> str:
        normalized_prompt = prompt.strip()
        if not normalized_prompt:
            raise ValueError("Prompt cannot be empty")
        return normalized_prompt

    def _options(self) -> dict[str, float | int]:
        return {
            "temperature": self.temperature,
            "num_predict": self.max_tokens,
        }

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Return a complete Ollama response."""
        try:
            response = self.client.generate(
                model=self.model,
                prompt=self._validate_prompt(prompt),
                system=system_prompt or "",
                options=self._options(),
                keep_alive=self.keep_alive,
                stream=False,
            )
        except (httpx.HTTPError, ResponseError) as error:
            raise LLMServiceError("Ollama generation failed") from error
        return response.response.strip()

    def stream_generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> Iterator[str]:
        """Yield non-empty text fragments from Ollama's response stream."""
        try:
            stream = self.client.generate(
                model=self.model,
                prompt=self._validate_prompt(prompt),
                system=system_prompt or "",
                options=self._options(),
                keep_alive=self.keep_alive,
                stream=True,
            )
            for part in stream:
                if part.response:
                    yield part.response
        except (httpx.HTTPError, ResponseError) as error:
            raise LLMServiceError("Ollama streaming failed") from error


@lru_cache(maxsize=1)
def get_llm_service() -> LLMProvider:
    """Create and cache the configured LLM provider."""
    settings = get_settings()
    if not 0 <= settings.llm_temperature <= 2:
        raise ValueError("LLM_TEMPERATURE must be between 0 and 2")
    if settings.llm_max_tokens < 1:
        raise ValueError("LLM_MAX_TOKENS must be positive")
    return OllamaLLM(
        client=Client(
            host=settings.ollama_url,
            timeout=settings.ollama_timeout_seconds,
        ),
        model=settings.ollama_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        keep_alive=settings.llm_keep_alive,
    )

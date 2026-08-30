"""Cached local BGE embeddings through LangChain."""

from functools import lru_cache

import torch
from langchain_huggingface import HuggingFaceEmbeddings

from app.config import get_settings

QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


def resolve_device(configured_device: str) -> str:
    """Use CUDA automatically when available, with a safe CPU fallback."""
    if configured_device != "auto":
        if configured_device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("EMBEDDING_DEVICE=cuda but CUDA is unavailable to PyTorch")
        return configured_device
    return "cuda" if torch.cuda.is_available() else "cpu"


@lru_cache(maxsize=1)
def load_model() -> HuggingFaceEmbeddings:
    """Load and cache one embedding-model instance per application process."""
    settings = get_settings()
    return HuggingFaceEmbeddings(
        model_name=settings.embedding_model,
        model_kwargs={"device": resolve_device(settings.embedding_device)},
        encode_kwargs={
            "normalize_embeddings": True,
            "batch_size": settings.embedding_batch_size,
        },
        query_encode_kwargs={
            "normalize_embeddings": True,
            "prompt": QUERY_INSTRUCTION,
        },
    )


def embed_text(text: str) -> list[float]:
    """Embed one document passage."""
    return embed_texts([text])[0]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed document passages in a batch."""
    if not texts:
        return []
    return load_model().embed_documents(texts)


def embed_query(question: str) -> list[float]:
    """Embed a retrieval query using the BGE query instruction."""
    return load_model().embed_query(question)

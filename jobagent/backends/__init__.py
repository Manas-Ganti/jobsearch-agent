"""Model inference behind protocols. Swapping a model is a config change."""

from .embeddings import (
    EMBEDDING_BACKENDS,
    EmbeddingBackend,
    build_embeddings,
    cosine,
)
from .llm import LLM_BACKENDS, LLMBackend, build_llm, complete_model

__all__ = [
    "EMBEDDING_BACKENDS",
    "EmbeddingBackend",
    "LLM_BACKENDS",
    "LLMBackend",
    "build_embeddings",
    "build_llm",
    "complete_model",
    "cosine",
]

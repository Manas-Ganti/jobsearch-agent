"""EmbeddingBackend protocol + implementations."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, Sequence, runtime_checkable

import httpx

from ..registry import Registry

EMBEDDING_BACKENDS: Registry["EmbeddingBackend"] = Registry("embedding backend")


@runtime_checkable
class EmbeddingBackend(Protocol):
    model: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """One vector per input, same order."""


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return num / (na * nb) if na and nb else 0.0


@EMBEDDING_BACKENDS.register("ollama")
class OllamaEmbeddings:
    def __init__(
        self,
        model: str = "bge-m3",
        base_url: str = "http://localhost:11434",
        options: dict | None = None,
        batch_size: int = 16,
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.batch_size = int((options or {}).get("batch_size", batch_size))
        self._client = httpx.Client(timeout=timeout)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = list(texts[i : i + self.batch_size])
            resp = self._client.post(
                f"{self.base_url}/api/embed", json={"model": self.model, "input": batch}
            )
            resp.raise_for_status()
            out.extend(resp.json()["embeddings"])
        return out


@EMBEDDING_BACKENDS.register("openai_compatible")
class OpenAICompatibleEmbeddings:
    """vLLM / any /v1/embeddings server."""

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:8000/v1",
        options: dict | None = None,
        api_key: str = "EMPTY",
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.batch_size = int((options or {}).get("batch_size", 16))
        self._client = httpx.Client(
            timeout=timeout, headers={"Authorization": f"Bearer {api_key}"}
        )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            resp = self._client.post(
                f"{self.base_url}/embeddings",
                json={"model": self.model, "input": list(texts[i : i + self.batch_size])},
            )
            resp.raise_for_status()
            out.extend(item["embedding"] for item in resp.json()["data"])
        return out


@EMBEDDING_BACKENDS.register("hashing")
class HashingEmbeddings:
    """Dependency-free fallback: hashed bag-of-words. Not as good as a real
    embedding model, but deterministic and offline — used by tests and by
    `--offline` smoke runs."""

    _token = re.compile(r"[a-z0-9+#.]+")

    def __init__(self, model: str = "hashing", dim: int = 512, **_: object) -> None:
        self.model = model
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in self._token.findall(text.lower()):
            h = int.from_bytes(hashlib.md5(tok.encode()).digest()[:4], "big")
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec


def build_embeddings(cfg) -> EmbeddingBackend:
    EMBEDDING_BACKENDS.discover(__package__)
    return EMBEDDING_BACKENDS.create(
        cfg.backend, model=cfg.model, base_url=cfg.base_url, options=cfg.options
    )

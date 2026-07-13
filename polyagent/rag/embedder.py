"""Embedder abstraction + a deterministic offline default.

``HashEmbedder`` produces a stable, normalised vector from text via salted
hashing. It has NO real semantic meaning — it exists so the whole retrieval
pipeline runs offline and is unit-testable. Swap in an OpenAI/DeepSeek/sentence
embedder in production; the contract is identical.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Protocol


class Embedder(Protocol):
    dim: int

    async def embed(self, text: str) -> list[float]: ...


class HashEmbedder:
    dim = 256

    async def embed(self, text: str) -> list[float]:
        data = text.encode("utf-8")
        vec = [0.0] * self.dim
        for i in range(self.dim):
            digest = hashlib.sha256(data + i.to_bytes(4, "big")).digest()
            vec[i] = int.from_bytes(digest[:8], "big") / (2**64 - 1) - 0.5
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


class FastEmbedEmbedder:
    """Real semantic embedder backed by ``fastembed`` (ONNX, local, no torch).

    Note: DeepSeek has NO embedding API (/v1/embeddings returns 404), so for real
    semantic vectors we use a local ONNX model. The model downloads on first use
    (~80MB) and is cached. ``model_name`` defaults to a multilingual MiniLM.
    """

    _DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or self._DEFAULT_MODEL
        self._model: Any = None
        self._dim: int | None = None

    def _ensure(self) -> None:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name)

    @property
    def dim(self) -> int:
        if self._dim is None:
            self._dim = len(next(iter(self._model.embed(["probe"])))) if self._model else 0
        return self._dim

    async def embed(self, text: str) -> list[float]:
        import asyncio

        self._ensure()
        assert self._model is not None
        return await asyncio.to_thread(lambda: list(next(iter(self._model.embed([text])))))

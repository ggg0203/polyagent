"""VectorStore abstraction + an in-memory cosine implementation.

Pluggable: default ``InMemoryVectorStore`` keeps everything in a list and does
a linear cosine scan — fine for tests/demos. Production swaps in chromadb or
pgvector behind the same protocol.
"""

from __future__ import annotations

import math
from typing import Any, Protocol, TypeAlias

Hit: TypeAlias = tuple[str, float, dict[str, Any]]


class VectorStore(Protocol):
    async def add(self, id: str, vector: list[float], metadata: dict[str, Any]) -> None: ...

    async def query(self, vector: list[float], k: int) -> list[Hit]: ...


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._items: list[tuple[str, list[float], dict[str, Any]]] = []

    async def add(self, id: str, vector: list[float], metadata: dict[str, Any]) -> None:
        self._items.append((id, vector, dict(metadata)))

    async def query(self, vector: list[float], k: int) -> list[Hit]:
        scored = [(id, _cosine(vector, v), meta) for id, v, meta in self._items]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def __len__(self) -> int:
        return len(self._items)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


class ChromaVectorStore:
    """Persistent vector store backed by chromadb.

    Stores pre-computed vectors (the Embedder generates them; chromadb only indexes).
    Distances are converted to similarity scores so the protocol matches InMemory.
    """

    def __init__(self, collection_name: str = "polyagent", path: str = "./chroma") -> None:
        import chromadb

        self._client = chromadb.PersistentClient(path=path)
        self._collection = self._client.get_or_create_collection(collection_name)

    async def add(self, id: str, vector: list[float], metadata: dict[str, Any]) -> None:
        import asyncio

        await asyncio.to_thread(
            self._collection.upsert,
            ids=[id],
            embeddings=[vector],  # type: ignore[arg-type]  # chromadb type stubs vs runtime
            metadatas=[metadata],
        )

    async def query(self, vector: list[float], k: int) -> list[Hit]:
        import asyncio

        results = await asyncio.to_thread(
            self._collection.query,
            query_embeddings=[vector],  # type: ignore[arg-type]  # chromadb type stubs vs runtime
            n_results=k,
        )
        ids = (results.get("ids") or [[]])[0]
        dists = (results.get("distances") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        return [(i, 1.0 / (1.0 + d), dict(m)) for i, d, m in zip(ids, dists, metas, strict=True)]

    def __len__(self) -> int:
        return int(self._collection.count())

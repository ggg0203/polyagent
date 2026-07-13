"""VectorMemory — long-term memory backed by an embedder + vector store.

Each record is embedded and stored; retrieval returns the top-k most similar
records to the query. The store is pluggable (InMemoryVectorStore by default,
chromadb in production) so the abstraction stays provider-agnostic.
"""

from __future__ import annotations

from polyagent.memory.base import MemoryRecord
from polyagent.rag.embedder import Embedder
from polyagent.rag.vectorstore import VectorStore


class VectorMemory:
    def __init__(self, embedder: Embedder, store: VectorStore) -> None:
        self.embedder = embedder
        self.store = store

    async def add(self, record: MemoryRecord) -> None:
        vector = await self.embedder.embed(record.content)
        await self.store.add(record.id, vector, record.model_dump())

    async def retrieve(self, query: str, k: int = 4) -> list[MemoryRecord]:
        query_vector = await self.embedder.embed(query)
        hits = await self.store.query(query_vector, k)
        records: list[MemoryRecord] = []
        for _id, _score, meta in hits:
            if "role" in meta and "content" in meta:
                records.append(MemoryRecord(**meta))
        return records

"""Document + RAGIndex: load -> split -> embed -> store -> retrieve."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from polyagent.rag.embedder import Embedder
from polyagent.rag.splitter import TextSplitter
from polyagent.rag.vectorstore import VectorStore


class Document(BaseModel):
    id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RAGIndex:
    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        splitter: TextSplitter | None = None,
    ) -> None:
        self.embedder = embedder
        self.store = store
        self.splitter = splitter or TextSplitter()

    async def add_documents(self, documents: list[Document]) -> int:
        added = 0
        for doc in documents:
            for chunk in self.splitter.split(doc.content):
                vector = await self.embedder.embed(chunk)
                chunk_id = f"{doc.id}:{uuid.uuid4().hex[:8]}"
                meta = {"content": chunk, "doc_id": doc.id, **doc.metadata}
                await self.store.add(chunk_id, vector, meta)
                added += 1
        return added

    async def query(self, text: str, k: int = 4) -> list[Document]:
        query_vector = await self.embedder.embed(text)
        hits = await self.store.query(query_vector, k)
        results: list[Document] = []
        for chunk_id, _score, meta in hits:
            content = meta.get("content", "")
            meta_out = {kk: vv for kk, vv in meta.items() if kk != "content"}
            results.append(Document(id=chunk_id, content=content, metadata=meta_out))
        return results

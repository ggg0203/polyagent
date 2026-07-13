"""RAG: embedder, vector store, splitter, document index."""

from __future__ import annotations

import math

import pytest

from polyagent.rag import (
    Document,
    HashEmbedder,
    InMemoryVectorStore,
    RAGIndex,
    TextSplitter,
)


async def test_hash_embedder_deterministic_and_normalised() -> None:
    emb = HashEmbedder()
    a = await emb.embed("hello")
    b = await emb.embed("hello")
    assert a == b
    assert len(a) == HashEmbedder.dim
    assert math.isclose(sum(x * x for x in a), 1.0, abs_tol=1e-6)


async def test_inmemory_vectorstore_ranks_by_cosine() -> None:
    store = InMemoryVectorStore()
    emb = HashEmbedder()
    await store.add("a", await emb.embed("alpha"), {})
    await store.add("b", await emb.embed("beta"), {})
    hits = await store.query(await emb.embed("alpha"), k=2)
    assert hits[0][0] == "a"
    assert hits[0][1] > hits[1][1]


def test_splitter_chunks_with_overlap() -> None:
    sp = TextSplitter(chunk_size=10, chunk_overlap=3)
    chunks = sp.split("abcdefghijklmnopqrstuvwxyz")
    assert len(chunks) >= 2
    assert chunks[1].startswith("h")  # step = 7 -> second chunk starts at index 7


def test_splitter_rejects_overlap_ge_size() -> None:
    with pytest.raises(ValueError):
        TextSplitter(chunk_size=10, chunk_overlap=10)


def test_splitter_short_text_returns_single_chunk() -> None:
    sp = TextSplitter(chunk_size=100, chunk_overlap=10)
    assert sp.split("short") == ["short"]


async def test_rag_index_add_and_query() -> None:
    index = RAGIndex(HashEmbedder(), InMemoryVectorStore())
    added = await index.add_documents(
        [
            Document(id="d1", content="python is a programming language"),
            Document(id="d2", content="the cat sat on the mat"),
        ]
    )
    assert added == 2
    results = await index.query("python is a programming language", k=1)
    assert len(results) == 1
    assert "python" in results[0].content

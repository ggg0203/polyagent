"""Memory: buffer, vector memory, compressors."""

from __future__ import annotations

from polyagent.core.types import Message, Role
from polyagent.llm.client import LLMClient
from polyagent.llm.mock import MockProvider
from polyagent.llm.types import LLMResponse
from polyagent.memory import (
    ConversationBuffer,
    MemoryRecord,
    SummarizingCompressor,
    TokenWindowCompressor,
    VectorMemory,
)
from polyagent.rag import HashEmbedder, InMemoryVectorStore


async def test_buffer_drops_oldest_when_full() -> None:
    buf = ConversationBuffer(max_messages=3)
    for i in range(5):
        await buf.add(MemoryRecord(id=str(i), role="user", content=f"msg {i}"))
    assert len(buf) == 3  # maxlen dropped the oldest 2
    msgs = buf.messages_for_context()
    assert msgs[0].content == "msg 2"


async def test_buffer_retrieve_returns_recent_k() -> None:
    buf = ConversationBuffer()
    for i in range(6):
        await buf.add(MemoryRecord(id=str(i), role="user", content=f"msg {i}"))
    recs = await buf.retrieve("anything", k=2)
    assert [r.content for r in recs] == ["msg 4", "msg 5"]


async def test_vector_memory_retrieves_most_similar() -> None:
    mem = VectorMemory(HashEmbedder(), InMemoryVectorStore())
    await mem.add(MemoryRecord(id="1", role="user", content="the quick brown fox"))
    await mem.add(MemoryRecord(id="2", role="user", content="lorem ipsum dolor sit"))
    recs = await mem.retrieve("the quick brown fox", k=1)
    assert len(recs) == 1
    assert recs[0].content == "the quick brown fox"


def test_token_window_compressor_keeps_recent_only() -> None:
    msgs = [Message(role=Role.USER, content="x" * 100) for _ in range(10)]
    comp = TokenWindowCompressor(max_tokens=60)  # ~2 messages of est 26 each
    kept = comp.compress(msgs)
    assert len(kept) == 2
    assert kept[0] is msgs[8]
    assert kept[-1] is msgs[9]


async def test_summarizing_compressor_uses_llm() -> None:
    provider = MockProvider(script=[LLMResponse(content="SUMMARY", model="mock")])
    client = LLMClient(provider)
    comp = SummarizingCompressor(client, model="mock", keep_recent=2)
    msgs = [Message(role=Role.USER, content=f"turn {i}") for i in range(5)]
    result = await comp.compress(msgs)
    assert result[0].role == Role.SYSTEM
    assert "SUMMARY" in result[0].content
    assert len(result) == 3  # 1 summary + 2 recent
    assert result[1].content == "turn 3"
    assert result[2].content == "turn 4"

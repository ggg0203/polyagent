"""ConversationBuffer — short-term memory, FIFO with a max length."""

from __future__ import annotations

from collections import deque

from polyagent.core.types import Message
from polyagent.memory.base import MemoryRecord


class ConversationBuffer:
    def __init__(self, max_messages: int = 20) -> None:
        self._records: deque[MemoryRecord] = deque(maxlen=max_messages)

    async def add(self, record: MemoryRecord) -> None:
        self._records.append(record)

    async def retrieve(self, query: str, k: int = 4) -> list[MemoryRecord]:
        items = list(self._records)
        return items[-k:] if len(items) > k else items

    def messages_for_context(self) -> list[Message]:
        return [r.to_message() for r in self._records]

    def __len__(self) -> int:
        return len(self._records)

"""Memory abstractions: records + the Memory protocol.

A ``Memory`` stores conversation turns and retrieves the ones relevant to a
query (recent-only for a buffer, similarity-ranked for vector memory).
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from polyagent.core.types import Message, Role


class MemoryRecord(BaseModel):
    id: str
    role: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_message(self) -> Message:
        return Message(role=Role(self.role), content=self.content)


class Memory(Protocol):
    """Pluggable memory backend."""

    async def add(self, record: MemoryRecord) -> None: ...

    async def retrieve(self, query: str, k: int = 4) -> list[MemoryRecord]: ...

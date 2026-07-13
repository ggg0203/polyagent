"""LLMProvider protocol — the contract every backend implements."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from polyagent.llm.types import LLMRequest, LLMResponse


@runtime_checkable
class LLMProvider(Protocol):
    """A pluggable LLM backend.

    Implementations must be safe to call concurrently. `chat` is async so
    providers can stream / multiplex I/O. Tool/function-calling lands in M2;
    until then requests carry only messages.
    """

    @property
    def name(self) -> str: ...

    async def chat(self, request: LLMRequest) -> LLMResponse: ...

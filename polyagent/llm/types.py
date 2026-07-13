"""Request / response types for LLM calls."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from polyagent.core.types import Message, ToolCall, Usage


class LLMRequest(BaseModel):
    model: str
    messages: list[Message]
    temperature: float = 0.7
    max_tokens: int | None = None
    tools: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    content: str
    model: str
    usage: Usage = Field(default_factory=Usage)
    finish_reason: str | None = None
    tool_calls: list[ToolCall] | None = None
    raw: dict[str, Any] | None = None

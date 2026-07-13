"""Core domain types: messages, usage, cost, pricing, agent spec.

These are the *provider-agnostic* contracts the rest of the framework builds on.
No HTTP, no provider specifics here.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    """A single function-call request emitted by the model (OpenAI convention).

    ``arguments`` is a JSON string so it round-trips to providers unchanged.
    """

    id: str
    name: str
    arguments: str


class Message(BaseModel):
    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None


class Usage(BaseModel):
    """Token accounting for a single LLM response."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: Usage) -> Usage:
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


class ModelPricing(BaseModel):
    """USD per 1,000,000 tokens (input / output)."""

    input_per_1m: float = 0.0
    output_per_1m: float = 0.0


PRICING: dict[str, ModelPricing] = {
    "deepseek-chat": ModelPricing(input_per_1m=0.27, output_per_1m=1.10),
    "deepseek-reasoner": ModelPricing(input_per_1m=0.55, output_per_1m=2.19),
    "mock": ModelPricing(),
}


class CostReport(BaseModel):
    """Accumulated token usage + estimated monetary cost for a run."""

    usage: Usage = Field(default_factory=Usage)
    estimated_cost_usd: float = 0.0

    def add_usage(self, usage: Usage, model: str) -> None:
        self.usage = self.usage.add(usage)
        pricing = PRICING.get(model, ModelPricing())
        self.estimated_cost_usd += (
            usage.prompt_tokens * pricing.input_per_1m / 1_000_000.0
            + usage.completion_tokens * pricing.output_per_1m / 1_000_000.0
        )


class AgentSpec(BaseModel):
    """Declarative description of an Agent role + model + behaviour."""

    name: str
    role: str  # "planner" | "worker" | "critic" | "synthesizer"
    system_prompt: str = ""
    model: str = "deepseek-chat"
    temperature: float = 0.7
    max_retries: int = 3

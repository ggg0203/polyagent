"""Core: domain types, exceptions, and a single-turn Agent.

Provider-agnostic contracts (messages, usage/cost, agent spec, exceptions) plus
``Agent`` — one role that completes one LLM turn via an ``LLMClient``.

``Agent`` is imported lazily (PEP 562) because it depends on ``llm`` (for the
tool loop), which would otherwise create a circular import at package init.
"""

from polyagent.core.exceptions import (
    BudgetExceededError,
    LLMError,
    ProviderUnavailableError,
    RateLimitError,
    RetryableError,
    TimeoutError,
)
from polyagent.core.types import (
    PRICING,
    AgentSpec,
    CostReport,
    Message,
    ModelPricing,
    Role,
    Usage,
)

__all__ = [
    "Agent",
    "AgentSpec",
    "BudgetExceededError",
    "CostReport",
    "LLMError",
    "Message",
    "ModelPricing",
    "PRICING",
    "ProviderUnavailableError",
    "RateLimitError",
    "RetryableError",
    "Role",
    "TimeoutError",
    "Usage",
]


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    if name == "Agent":
        from polyagent.core.agent import Agent

        return Agent
    raise AttributeError(f"module 'polyagent.core' has no attribute {name!r}")


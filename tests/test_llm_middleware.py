"""Reliability middleware: retry, fallback, budget, cost, chain order."""

from __future__ import annotations

from typing import Any

import pytest

from polyagent.core.exceptions import (
    BudgetExceededError,
    ProviderUnavailableError,
    RateLimitError,
)
from polyagent.core.types import CostReport, Message, Role, Usage
from polyagent.llm.client import LLMClient
from polyagent.llm.middleware import (
    BudgetMiddleware,
    CostAccountMiddleware,
    FallbackMiddleware,
    Middleware,
    RetryMiddleware,
)
from polyagent.llm.mock import MockProvider
from polyagent.llm.types import LLMRequest, LLMResponse


def _req(text: str = "hi", model: str = "mock") -> LLMRequest:
    return LLMRequest(model=model, messages=[Message(role=Role.USER, content=text)])


def _resp(text: str = "ok", model: str = "mock") -> LLMResponse:
    return LLMResponse(
        content=text,
        model=model,
        usage=Usage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
    )


async def _no_sleep(_delay: float) -> None:
    return None


async def test_retry_recovers_after_transient_error() -> None:
    prov = MockProvider(script=[RateLimitError("429", retry_after=0), _resp()])
    client = LLMClient(prov, [RetryMiddleware(max_retries=2, sleep=_no_sleep)])
    resp = await client.chat(_req())
    assert resp.content == "ok"
    assert len(prov.calls) == 2  # failed once, then succeeded


async def test_retry_gives_up_after_max() -> None:
    prov = MockProvider(script=[RateLimitError("429"), RateLimitError("429")])
    client = LLMClient(prov, [RetryMiddleware(max_retries=1, sleep=_no_sleep)])
    with pytest.raises(RateLimitError):
        await client.chat(_req())
    assert len(prov.calls) == 2  # initial attempt + 1 retry


async def test_fallback_to_secondary_on_primary_failure() -> None:
    primary = MockProvider(script=[ProviderUnavailableError("down")])
    secondary = MockProvider(script=[_resp("from-secondary")])
    client = LLMClient(primary, [FallbackMiddleware([secondary])])
    resp = await client.chat(_req())
    assert resp.content == "from-secondary"
    assert len(secondary.calls) == 1


async def test_budget_aborts_when_exhausted() -> None:
    report = CostReport()
    report.usage = Usage(total_tokens=100)
    client = LLMClient(MockProvider(), [BudgetMiddleware(report, budget_tokens=100)])
    with pytest.raises(BudgetExceededError):
        await client.chat(_req())


async def test_cost_accounts_usage_and_money() -> None:
    report = CostReport()
    client = LLMClient(
        MockProvider(script=[_resp(model="deepseek-chat"), _resp(model="deepseek-chat")]),
        [CostAccountMiddleware(report)],
    )
    await client.chat(_req())
    await client.chat(_req())
    # 2 responses x (5 prompt + 5 completion) tokens
    assert report.usage.prompt_tokens == 10
    assert report.usage.completion_tokens == 10
    assert report.estimated_cost_usd > 0


async def test_chain_executes_outermost_first() -> None:
    order: list[str] = []

    class _Recorder:
        def __init__(self, tag: str) -> None:
            self.tag = tag

        async def __call__(self, request: LLMRequest, call_next: Any) -> LLMResponse:
            order.append(f"{self.tag}-in")
            resp = await call_next(request)
            order.append(f"{self.tag}-out")
            return resp

    middlewares: list[Middleware] = [_Recorder("A"), _Recorder("B")]
    client = LLMClient(MockProvider(script=[_resp()]), middlewares)
    await client.chat(_req())
    assert order == ["A-in", "B-in", "B-out", "A-out"]

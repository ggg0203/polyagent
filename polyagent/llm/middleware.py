"""Reliability middleware: composable wrappers around an LLM call.

Each middleware has signature ``async (request, call_next) -> response``.
A chain is built right-to-left so the *first* middleware in the list runs
outermost (sees the request first, the response last).

Chain::

    request -> [RateLimit] -> [Retry] -> [Fallback] -> [Budget] -> [Cost]
            -> provider.chat() -> [Cost] -> ... -> response
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from typing import Protocol

from polyagent.core.exceptions import (
    BudgetExceededError,
    LLMError,
    ProviderUnavailableError,
    RateLimitError,
    RetryableError,
    TimeoutError,
)
from polyagent.core.types import CostReport
from polyagent.llm.provider import LLMProvider
from polyagent.llm.types import LLMRequest, LLMResponse

Handler = Callable[[LLMRequest], Awaitable[LLMResponse]]


class Middleware(Protocol):
    async def __call__(self, request: LLMRequest, call_next: Handler) -> LLMResponse: ...


def build_chain(middlewares: list[Middleware], terminal: Handler) -> Handler:
    """Compose middlewares around a terminal handler."""

    async def base(req: LLMRequest) -> LLMResponse:
        return await terminal(req)

    handler: Handler = base
    for mw in reversed(middlewares):
        handler = _wrap(mw, handler)
    return handler


def _wrap(mw: Middleware, nxt: Handler) -> Handler:
    async def wrapped(req: LLMRequest) -> LLMResponse:
        return await mw(req, nxt)

    return wrapped


# --------------------------------------------------------------------------- #
# Individual middlewares
# --------------------------------------------------------------------------- #


class RetryMiddleware:
    """Exponential backoff + jitter. Honours ``RateLimitError.retry_after``.

    ``sleep`` is injectable so tests can run without real delays.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 0.1,
        max_delay: float = 10.0,
        retry_on: tuple[type[Exception], ...] = (RetryableError,),
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.retry_on = retry_on
        self._sleep = sleep or asyncio.sleep

    async def __call__(self, request: LLMRequest, call_next: Handler) -> LLMResponse:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await call_next(request)
            except self.retry_on as exc:
                last_exc = exc
                if attempt == self.max_retries:
                    break
                if isinstance(exc, RateLimitError) and exc.retry_after is not None:
                    delay = exc.retry_after
                else:
                    delay = min(self.base_delay * (2**attempt), self.max_delay)
                    delay += random.uniform(0, delay * 0.1)
                await self._sleep(delay)
        assert last_exc is not None
        raise last_exc


class RateLimitMiddleware:
    """Concurrency cap + minimum spacing between calls (simple rate limiting)."""

    def __init__(self, max_concurrency: int = 4, min_interval: float = 0.0) -> None:
        self._sem = asyncio.Semaphore(max_concurrency)
        self._min_interval = min_interval
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def __call__(self, request: LLMRequest, call_next: Handler) -> LLMResponse:
        async with self._sem:
            if self._min_interval > 0:
                async with self._lock:
                    now = time.monotonic()
                    wait = max(0.0, self._last + self._min_interval - now)
                    if wait > 0:
                        await asyncio.sleep(wait)
                    self._last = time.monotonic()
            return await call_next(request)


class FallbackMiddleware:
    """If the primary handler (and retry chain) fails, try backup providers in order."""

    def __init__(self, fallback_providers: list[LLMProvider]) -> None:
        self.fallback_providers = fallback_providers

    async def __call__(self, request: LLMRequest, call_next: Handler) -> LLMResponse:
        try:
            return await call_next(request)
        except (ProviderUnavailableError, RateLimitError, TimeoutError) as primary_exc:
            last_exc: Exception = primary_exc
            for prov in self.fallback_providers:
                try:
                    return await prov.chat(request)
                except LLMError as exc:
                    last_exc = exc
            raise last_exc from primary_exc


class BudgetMiddleware:
    """Abort before a call if the run has already consumed its token budget."""

    def __init__(self, cost_report: CostReport, budget_tokens: int) -> None:
        self.cost_report = cost_report
        self.budget_tokens = budget_tokens

    async def __call__(self, request: LLMRequest, call_next: Handler) -> LLMResponse:
        used = self.cost_report.usage.total_tokens
        if used >= self.budget_tokens:
            raise BudgetExceededError(
                f"budget exhausted: {used}/{self.budget_tokens} tokens already used"
            )
        return await call_next(request)


class CostAccountMiddleware:
    """Accumulate per-response usage into a shared CostReport."""

    def __init__(self, cost_report: CostReport) -> None:
        self.cost_report = cost_report

    async def __call__(self, request: LLMRequest, call_next: Handler) -> LLMResponse:
        response = await call_next(request)
        self.cost_report.add_usage(response.usage, response.model)
        return response

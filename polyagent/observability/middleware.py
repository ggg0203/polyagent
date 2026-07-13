"""ObservabilityMiddleware — auto-traces every LLM call + records metrics/logs.

Drop this into an LLMClient's middleware chain and every ``chat()`` becomes a
span in the current trace (nested under whatever outer span is active), with
token/call/error counters bumped automatically.
"""

from __future__ import annotations

from typing import Any

from polyagent.llm.middleware import Handler
from polyagent.llm.types import LLMRequest, LLMResponse
from polyagent.observability.metrics import Metrics
from polyagent.observability.tracer import Tracer


class ObservabilityMiddleware:
    def __init__(
        self,
        tracer: Tracer,
        metrics: Metrics | None = None,
        logger: Any = None,
    ) -> None:
        self.tracer = tracer
        self.metrics = metrics
        self.logger = logger

    async def __call__(self, request: LLMRequest, call_next: Handler) -> LLMResponse:
        attrs: dict[str, Any] = {"model": request.model, "messages": len(request.messages)}
        with self.tracer.span("llm.chat", **attrs):
            try:
                resp = await call_next(request)
            except Exception:
                if self.metrics:
                    self.metrics.inc("llm.errors")
                raise
            if self.metrics:
                self.metrics.inc("llm.calls")
                self.metrics.inc("llm.tokens", resp.usage.total_tokens)
            if self.logger:
                self.logger.info(
                    "llm_call", model=request.model, tokens=resp.usage.total_tokens
                )
            return resp

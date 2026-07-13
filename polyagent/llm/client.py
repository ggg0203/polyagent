"""LLMClient — the public entrypoint agents use.

Wraps a single provider + a reliability middleware chain so callers never
touch provider or retry details directly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from polyagent.llm.middleware import Handler, Middleware, build_chain
from polyagent.llm.provider import LLMProvider
from polyagent.llm.types import LLMRequest, LLMResponse


class LLMClient:
    def __init__(
        self,
        provider: LLMProvider,
        middlewares: list[Middleware] | None = None,
    ) -> None:
        self.provider = provider

        async def terminal(req: LLMRequest) -> LLMResponse:
            return await provider.chat(req)

        self._handler: Handler = build_chain(middlewares or [], terminal)

    async def chat(self, request: LLMRequest) -> LLMResponse:
        return await self._handler(request)

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream content deltas straight from the provider (no middleware).

        Reliability middleware still wraps non-streaming ``chat``; streaming is for
        interactive display.
        """
        stream_fn = getattr(self.provider, "stream", None)
        if stream_fn is None:
            msg = f"provider {self.provider.name!r} does not support streaming"
            raise TypeError(msg)
        async for chunk in stream_fn(request):
            yield chunk

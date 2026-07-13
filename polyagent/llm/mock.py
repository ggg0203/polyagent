"""MockProvider — deterministic, offline, no network/keys needed.

Supports a *script* of pre-canned responses / exceptions for testing retry and
fallback logic, and an echo fallback when the script is exhausted.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from polyagent.core.types import Role, Usage
from polyagent.llm.types import LLMRequest, LLMResponse


class MockProvider:
    def __init__(
        self,
        *,
        name: str = "mock",
        script: list[LLMResponse | Exception] | None = None,
        default: LLMResponse | None = None,
    ) -> None:
        self._name = name
        self.script: list[LLMResponse | Exception] = list(script) if script else []
        self.default = default
        self._idx = 0
        self.calls: list[LLMRequest] = []

    @property
    def name(self) -> str:
        return self._name

    async def chat(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if self._idx < len(self.script):
            item = self.script[self._idx]
            self._idx += 1
            if isinstance(item, Exception):
                raise item
            return item
        if self.default is not None:
            return self.default
        return self._echo(request)

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Yield the echo response word-by-word (for offline stream testing)."""
        resp = await self.chat(request)
        for word in resp.content.split():
            yield word + " "

    @staticmethod
    def _echo(request: LLMRequest) -> LLMResponse:
        last_user = next((m for m in reversed(request.messages) if m.role == Role.USER), None)
        text = last_user.content if last_user else ""
        tokens = max(1, len(text) // 4)
        return LLMResponse(
            content=f"[mock] {text}",
            model=request.model,
            usage=Usage(
                prompt_tokens=tokens,
                completion_tokens=tokens,
                total_tokens=2 * tokens,
            ),
        )

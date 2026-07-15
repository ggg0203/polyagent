"""OpenAICompatibleProvider — works with any OpenAI ``/chat/completions`` endpoint.

Supports: DeepSeek, 阿里百炼 (DashScope), 通义千问, 百川, ZeroOne, Groq, Together,
OpenRouter, and any service that mirrors the OpenAI chat API.

Environment variables:
  LLM_API_KEY   — your API key (or pass directly)
  LLM_BASE_URL  — base URL of the provider (e.g. https://dashscope.aliyuncs.com/compatible-mode/v1)
  LLM_MODEL     — default model name (e.g. qwen-max, deepseek-chat, baichuan2-turbo)
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

from polyagent.core.exceptions import (
    ProviderUnavailableError,
    RateLimitError,
)
from polyagent.core.exceptions import (
    TimeoutError as LLMTimeoutError,
)
from polyagent.core.types import Message, ToolCall, Usage
from polyagent.llm.types import LLMRequest, LLMResponse


class OpenAICompatibleProvider:
    """Generic provider for any OpenAI-compatible chat API.

    Usage:
        provider = OpenAICompatibleProvider(
            api_key="sk-xxx",
            base_url="https://api.example.com/v1",
            model="qwen-max",
        )
        client = LLMClient(provider)
        resp = await client.chat(LLMRequest(model="qwen-max", messages=[...]))
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        model: str = "default",
        timeout: float = 60.0,
        name: str = "openai-compat",
    ) -> None:
        """Create an OpenAI-compatible provider.

        Args:
            api_key: API key. Falls back to LLM_API_KEY env var.
            base_url: Base URL (e.g. ``https://api.example.com/v1``).
                      Falls back to LLM_BASE_URL env var.
            model: Default model name. Falls back to LLM_MODEL env var.
            timeout: HTTP request timeout in seconds.
            name: Provider name for logs/metrics.
        """
        key = api_key or os.getenv("LLM_API_KEY")
        url = base_url or os.getenv("LLM_BASE_URL")
        mdl = model or os.getenv("LLM_MODEL") or "default"

        missing = []
        if not key:
            missing.append("LLM_API_KEY")
        if not url:
            missing.append("LLM_BASE_URL")
        if missing:
            raise ValueError(
                f"OpenAICompatibleProvider requires {' and '.join(missing)} "
                "(arg or env var)."
            )

        assert url, "LLM_BASE_URL must be set"
        self._api_key = key
        self._base_url = url.rstrip("/")
        self.default_model = mdl
        self._name = name
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )

    @property
    def name(self) -> str:
        return self._name

    async def chat(self, request: LLMRequest) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [self._to_openai(m) for m in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = request.tools

        try:
            resp = await self._client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(str(exc)) from exc

        if resp.status_code == 429:
            retry_after = _parse_retry_after(resp.headers.get("retry-after"))
            raise RateLimitError(f"{self.name} 429", retry_after=retry_after)
        if resp.status_code >= 500:
            raise ProviderUnavailableError(
                f"{self.name} {resp.status_code}: {resp.text[:200]}"
            )
        resp.raise_for_status()

        data = resp.json()
        choice = data["choices"][0]
        msg = choice["message"]
        usage_raw = data.get("usage") or {}
        usage = Usage(
            prompt_tokens=usage_raw.get("prompt_tokens", 0),
            completion_tokens=usage_raw.get("completion_tokens", 0),
            total_tokens=usage_raw.get("total_tokens", 0),
        )
        content = msg.get("content") or ""
        tool_calls, content = _extract_tool_calls(msg.get("tool_calls"), content)
        return LLMResponse(
            content=content,
            model=request.model,
            usage=usage,
            finish_reason=choice.get("finish_reason"),
            tool_calls=tool_calls,
            raw=data,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Yield content deltas from a streaming /chat/completions call."""
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [self._to_openai(m) for m in request.messages],
            "temperature": request.temperature,
            "stream": True,
        }
        if request.tools:
            payload["tools"] = request.tools
        try:
            async with self._client.stream(
                "POST", "/chat/completions", json=payload
            ) as resp:
                if resp.status_code == 429:
                    raise RateLimitError(f"{self.name} 429")
                if resp.status_code >= 500:
                    raise ProviderUnavailableError(
                        f"{self.name} {resp.status_code}"
                    )
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield content
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(str(exc)) from exc

    @staticmethod
    def _to_openai(m: Message) -> dict[str, Any]:
        item: dict[str, Any] = {"role": m.role.value, "content": m.content}
        if m.name:
            item["name"] = m.name
        if m.tool_calls:
            item["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": c.arguments},
                }
                for c in m.tool_calls
            ]
        if m.tool_call_id:
            item["tool_call_id"] = m.tool_call_id
        return item

    async def aclose(self) -> None:
        await self._client.aclose()


def _extract_tool_calls(
    raw: list[dict[str, Any]] | None, content: str
) -> tuple[list[ToolCall] | None, str]:
    """Return standard tool_calls if present."""
    if not raw:
        return None, content
    calls: list[ToolCall] = []
    for item in raw:
        fn = item.get("function") or {}
        calls.append(
            ToolCall(
                id=item.get("id", ""),
                name=fn.get("name", ""),
                arguments=fn.get("arguments", "{}"),
            )
        )
    return calls if calls else None, content


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None

"""DeepSeekProvider — OpenAI-compatible ``/chat/completions`` over httpx.

Not exercised by the offline test suite (no API key in CI); covered by MockProvider.
Real end-to-end run happens once the user supplies ``DEEPSEEK_API_KEY``.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx
import re

from polyagent.core.exceptions import (
    ProviderUnavailableError,
    RateLimitError,
)
from polyagent.core.exceptions import (
    TimeoutError as LLMTimeoutError,
)
from polyagent.core.types import Message, ToolCall, Usage
from polyagent.llm.types import LLMRequest, LLMResponse


class DeepSeekProvider:
    BASE_URL = "https://api.deepseek.com"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        model: str = "deepseek-chat",
        timeout: float = 60.0,
    ) -> None:
        key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not key:
            msg = "DeepSeekProvider requires an api key (arg or DEEPSEEK_API_KEY env var)."
            raise ValueError(msg)
        self._api_key = key
        self.base_url = base_url or self.BASE_URL
        self.default_model = model
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )

    @property
    def name(self) -> str:
        return "deepseek"

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
            raise RateLimitError("deepseek 429", retry_after=retry_after)
        if resp.status_code >= 500:
            raise ProviderUnavailableError(f"deepseek {resp.status_code}: {resp.text[:200]}")
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
        """Yield content deltas from a streaming /chat/completions call.

        Bypasses the middleware chain (retry/fallback/cost) — streaming is for
        interactive display; reliability middleware still wraps non-streaming ``chat``.
        """
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [self._to_openai(m) for m in request.messages],
            "temperature": request.temperature,
            "stream": True,
        }
        if request.tools:
            payload["tools"] = request.tools
        try:
            async with self._client.stream("POST", "/chat/completions", json=payload) as resp:
                if resp.status_code == 429:
                    raise RateLimitError("deepseek 429")
                if resp.status_code >= 500:
                    raise ProviderUnavailableError(f"deepseek {resp.status_code}")
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
    """Return standard tool_calls if present, otherwise parse DSML from content."""
    calls = _parse_tool_calls(raw)
    if calls:
        return calls, content
    dsml_calls = _parse_dsml(content)
    if dsml_calls:
        cleaned = _strip_dsml(content)
        return dsml_calls, cleaned
    return None, content


def _parse_tool_calls(raw: list[dict[str, Any]] | None) -> list[ToolCall] | None:
    if not raw:
        return None
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
    return calls


def _parse_dsml(content: str) -> list[ToolCall] | None:
    """Parse DeepSeek DSML tool-call markup embedded in content.

    DeepSeek sometimes returns tool calls like:
    <|DSML| |tool_calls>
    <|DSML| |invoke name="web_search">
    <|DSML| |parameter name="query" string="true">...</|DSML| |parameter>
    </|DSML| |invoke>
    </|DSML| |tool_calls>
    """
    if "<|DSML|" not in content:
        return None

    # Match invoke blocks with optional leading/trailing whitespace variants.
    invoke_pattern = re.compile(
        r"<\|DSML\|\s*\|invoke\s+name=\"([^\"]+)\">(.*?)<\/\|DSML\|\s*\|invoke>",
        re.DOTALL,
    )
    param_pattern = re.compile(
        r"<\|DSML\|\s*\|parameter\s+name=\"([^\"]+)\"(?:\s+\w+=\"[^\"]*\")*\s*>(.*?)<\/\|DSML\|\s*\|parameter>",
        re.DOTALL,
    )

    calls: list[ToolCall] = []
    for invoke_match in invoke_pattern.finditer(content):
        name = invoke_match.group(1)
        params_block = invoke_match.group(2)
        params: dict[str, str] = {}
        for param_match in param_pattern.finditer(params_block):
            param_name = param_match.group(1)
            param_value = param_match.group(2).strip()
            # Unescape common XML-ish entities.
            param_value = (
                param_value.replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&quot;", '"')
            )
            params[param_name] = param_value
        arguments = json.dumps(params, ensure_ascii=False) if params else "{}"
        calls.append(
            ToolCall(id=f"dsml_{len(calls)}", name=name, arguments=arguments)
        )

    return calls if calls else None


def _strip_dsml(content: str) -> str:
    """Remove DSML tool-call blocks from content, leaving only natural text."""
    # Remove whole tool_calls blocks first.
    cleaned = re.sub(
        r"<\|DSML\|\s*\|tool_calls\b[^>]*>.*?<\/\|DSML\|\s*\|tool_calls>",
        "",
        content,
        flags=re.DOTALL,
    )
    # Remove any leftover invoke/parameter blocks just in case.
    cleaned = re.sub(
        r"<\|DSML\|\s*\|invoke\b[^>]*>.*?<\/\|DSML\|\s*\|invoke>",
        "",
        cleaned,
        flags=re.DOTALL,
    )
    cleaned = re.sub(r"<\|DSML\|.*?>", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None

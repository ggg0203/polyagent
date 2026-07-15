"""DeepSeekProvider — extends OpenAICompatibleProvider with DeepSeek defaults + DSML parsing.

Environment variables (DeepSeek-specific, override generic LLM_* vars):
  DEEPSEEK_API_KEY  — your DeepSeek API key
  DEEPSEEK_MODEL    — model name (default: deepseek-chat)
  DEEPSEEK_BASE_URL — base URL (default: https://api.deepseek.com)
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator

from polyagent.core.types import ToolCall
from polyagent.llm.openai_compat import OpenAICompatibleProvider
from polyagent.llm.types import LLMRequest, LLMResponse


class DeepSeekProvider(OpenAICompatibleProvider):
    """DeepSeek LLM provider. Uses DEEPSEEK_* env vars with fallback to LLM_*.

    Also parses DeepSeek's DSML-style tool calls embedded in content.
    """

    BASE_URL = "https://api.deepseek.com"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        # Prefer DEEPSEEK_* env vars, fall back to generic LLM_*
        key = api_key or os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY")
        url = (
            base_url
            or os.getenv("DEEPSEEK_BASE_URL")
            or os.getenv("LLM_BASE_URL")
            or self.BASE_URL
        )
        mdl = model or os.getenv("DEEPSEEK_MODEL") or os.getenv("LLM_MODEL") or "deepseek-chat"

        if not key:
            raise ValueError(
                "DeepSeekProvider requires an api key "
                "(arg, DEEPSEEK_API_KEY, or LLM_API_KEY env var)."
            )

        super().__init__(
            api_key=key,
            base_url=url,
            model=mdl,
            timeout=timeout,
            name="deepseek",
        )

    @property
    def name(self) -> str:
        return "deepseek"

    async def chat(self, request: LLMRequest) -> LLMResponse:
        resp = await super().chat(request)
        if resp.tool_calls is None and resp.content:
            dsml_calls = _parse_dsml(resp.content)
            if dsml_calls:
                cleaned = _strip_dsml(resp.content)
                resp.tool_calls = dsml_calls
                resp.content = cleaned
        return resp

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        return super().stream(request)


def _parse_dsml(content: str) -> list[ToolCall] | None:
    """Parse DeepSeek DSML tool-call markup embedded in content."""
    if "<|DSML|" not in content:
        return None

    invoke_pattern = re.compile(
        r"<\|DSML\|\s*\|invoke\s+name=\"([^\"]+)\">(.*?)<\/\|DSML\|\s*\|invoke>",
        re.DOTALL,
    )
    param_pattern = re.compile(
        r"<\|DSML\|\s*\|parameter\s+name=\"([^\"]+)\"(?:\s+\w+=\"[^\"]*\")*\s*>"
        r"(.*?)<\/\|DSML\|\s*\|parameter>",
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
            param_value = (
                param_value.replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&quot;", '"')
            )
            params[param_name] = param_value
        arguments = json.dumps(params, ensure_ascii=False) if params else "{}"
        calls.append(ToolCall(id=f"dsml_{len(calls)}", name=name, arguments=arguments))

    return calls if calls else None


def _strip_dsml(content: str) -> str:
    """Remove DSML tool-call blocks from content."""
    cleaned = re.sub(
        r"<\|DSML\|\s*\|tool_calls\b[^>]*>.*?<\/\|DSML\|\s*\|tool_calls>",
        "",
        content,
        flags=re.DOTALL,
    )
    cleaned = re.sub(
        r"<\|DSML\|\s*\|invoke\b[^>]*>.*?<\/\|DSML\|\s*\|invoke>",
        "",
        cleaned,
        flags=re.DOTALL,
    )
    cleaned = re.sub(r"<\|DSML\|.*?>", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()

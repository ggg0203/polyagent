"""Agent: runs an LLM turn, with an optional tool-calling loop.

M1: single turn, no tools. M2: if a ``ToolRegistry`` is attached and the model
emits ``tool_calls``, the agent executes them, feeds results back as ``tool``
messages, and loops until the model produces a plain answer (or ``max_tool_iters``
is hit — a guard against infinite tool ping-pong).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from polyagent.core.types import AgentSpec, Message, Role
from polyagent.llm.client import LLMClient
from polyagent.llm.types import LLMRequest, LLMResponse
from polyagent.tools.base import ToolResult
from polyagent.tools.registry import ToolRegistry


class Agent:
    def __init__(
        self,
        spec: AgentSpec,
        client: LLMClient,
        tools: ToolRegistry | None = None,
        max_tool_iters: int = 5,
    ) -> None:
        self.spec = spec
        self.client = client
        self.tools = tools
        self.max_tool_iters = max_tool_iters

    async def run(self, user_input: str) -> LLMResponse:
        messages: list[Message] = []
        if self.spec.system_prompt:
            messages.append(Message(role=Role.SYSTEM, content=self.spec.system_prompt))
        messages.append(Message(role=Role.USER, content=user_input))

        tool_schemas = self.tools.schemas() if self.tools and len(self.tools) else None
        resp: LLMResponse | None = None

        for _ in range(self.max_tool_iters):
            request = LLMRequest(
                model=self.spec.model,
                messages=messages,
                temperature=self.spec.temperature,
                tools=tool_schemas,
            )
            resp = await self.client.chat(request)
            if not resp.tool_calls:
                return resp

            messages.append(
                Message(role=Role.ASSISTANT, content=resp.content, tool_calls=resp.tool_calls)
            )
            for call in resp.tool_calls:
                result = await self._exec_tool(call)
                messages.append(
                    Message(role=Role.TOOL, content=result.output, tool_call_id=call.id)
                )

        # Loop guard: out of iterations. Return the last response (may carry tool_calls).
        assert resp is not None
        return resp

    async def run_stream(self, user_input: str) -> AsyncIterator[str]:
        """Stream the model's answer (no tool loop). For interactive display."""
        messages: list[Message] = []
        if self.spec.system_prompt:
            messages.append(Message(role=Role.SYSTEM, content=self.spec.system_prompt))
        messages.append(Message(role=Role.USER, content=user_input))
        request = LLMRequest(
            model=self.spec.model,
            messages=messages,
            temperature=self.spec.temperature,
        )
        async for chunk in self.client.stream(request):
            yield chunk

    async def _exec_tool(self, call) -> ToolResult:  # type: ignore[no-untyped-def]
        if not self.tools:
            return ToolResult(output="no tools available", error=True)
        try:
            tool = self.tools.get(call.name)
        except KeyError:
            return ToolResult(output=f"unknown tool: {call.name}", error=True)
        try:
            args = json.loads(call.arguments) if call.arguments else {}
        except json.JSONDecodeError as exc:
            return ToolResult(output=f"invalid tool args json: {exc}", error=True)
        return await tool.call(args)

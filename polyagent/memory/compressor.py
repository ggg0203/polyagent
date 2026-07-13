"""Context compressors — keep messages within a token budget.

``TokenWindowCompressor`` keeps the most recent messages within an estimated
token budget (chars//4 proxy). ``SummarizingCompressor`` asks an LLM to
collapse older messages into one summary, keeping a window of recent turns verbatim.
"""

from __future__ import annotations

from polyagent.core.types import Message, Role
from polyagent.llm.client import LLMClient
from polyagent.llm.types import LLMRequest


class TokenWindowCompressor:
    """Drop oldest messages until the estimated token count fits the budget."""

    def __init__(self, max_tokens: int = 4000) -> None:
        self.max_tokens = max_tokens

    def compress(self, messages: list[Message]) -> list[Message]:
        if not messages:
            return []
        kept: list[Message] = []
        total = 0
        for msg in reversed(messages):
            est = len(msg.content) // 4 + 1
            if kept and total + est > self.max_tokens:
                break
            kept.append(msg)
            total += est
        kept.reverse()
        return kept


class SummarizingCompressor:
    """Summarize older messages into one system message; keep ``keep_recent`` verbatim."""

    def __init__(
        self,
        client: LLMClient,
        model: str,
        keep_recent: int = 4,
    ) -> None:
        self.client = client
        self.model = model
        self.keep_recent = keep_recent

    async def compress(self, messages: list[Message]) -> list[Message]:
        if len(messages) <= self.keep_recent:
            return list(messages)
        older = messages[: -self.keep_recent]
        recent = messages[-self.keep_recent:]
        summary = await self._summarize(older)
        summary_msg = Message(
            role=Role.SYSTEM, content=f"Summary of earlier conversation:\n{summary}"
        )
        return [summary_msg, *recent]

    async def _summarize(self, older: list[Message]) -> str:
        transcript = "\n".join(f"{m.role.value}: {m.content}" for m in older)
        request = LLMRequest(
            model=self.model,
            messages=[
                Message(role=Role.SYSTEM, content="Summarize the conversation concisely."),
                Message(role=Role.USER, content=transcript),
            ],
        )
        response = await self.client.chat(request)
        return response.content

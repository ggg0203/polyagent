"""MockProvider behaviour: echo fallback, script playback, call recording."""

from __future__ import annotations

import pytest

from polyagent.core.exceptions import RateLimitError
from polyagent.core.types import Message, Role, Usage
from polyagent.llm.mock import MockProvider
from polyagent.llm.types import LLMRequest, LLMResponse


def _req(text: str = "hello", model: str = "mock") -> LLMRequest:
    return LLMRequest(model=model, messages=[Message(role=Role.USER, content=text)])


async def test_echo_when_no_script() -> None:
    prov = MockProvider()
    resp = await prov.chat(_req("hello"))
    assert resp.content == "[mock] hello"
    assert resp.usage.total_tokens > 0


async def test_script_returns_items_in_order() -> None:
    r1 = LLMResponse(
        content="first", model="mock", usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    )
    r2 = LLMResponse(content="second", model="mock")
    prov = MockProvider(script=[r1, r2])
    assert (await prov.chat(_req("x"))).content == "first"
    assert (await prov.chat(_req("y"))).content == "second"


async def test_script_raises_then_echoes() -> None:
    prov = MockProvider(script=[RateLimitError("boom")])
    with pytest.raises(RateLimitError):
        await prov.chat(_req("x"))
    resp = await prov.chat(_req("after"))
    assert resp.content == "[mock] after"


async def test_calls_recorded() -> None:
    prov = MockProvider()
    await prov.chat(_req("a"))
    await prov.chat(_req("b"))
    assert len(prov.calls) == 2
    assert prov.calls[0].messages[0].content == "a"

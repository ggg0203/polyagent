"""Agent: single-turn conversation via LLMClient + Mock."""

from __future__ import annotations

from polyagent.core.agent import Agent
from polyagent.core.types import AgentSpec, Role
from polyagent.llm.client import LLMClient
from polyagent.llm.mock import MockProvider


async def test_agent_runs_one_turn() -> None:
    prov = MockProvider()
    client = LLMClient(prov)
    spec = AgentSpec(name="greeter", role="worker", system_prompt="be brief", model="mock")
    agent = Agent(spec, client)

    resp = await agent.run("hello")
    assert resp.content == "[mock] hello"

    sent = prov.calls[0].messages
    assert sent[0].role == Role.SYSTEM
    assert sent[0].content == "be brief"
    assert sent[1].role == Role.USER
    assert sent[1].content == "hello"


async def test_agent_without_system_prompt() -> None:
    prov = MockProvider()
    client = LLMClient(prov)
    agent = Agent(AgentSpec(name="raw", role="worker", model="mock"), client)
    await agent.run("ping")
    assert len(prov.calls[0].messages) == 1
    assert prov.calls[0].messages[0].role == Role.USER

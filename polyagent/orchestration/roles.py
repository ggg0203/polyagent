"""The four pipeline roles, each backed by an Agent.

Planner   -> splits a goal into a TaskNode DAG (JSON).
Worker    -> executes one task (optionally with tools).
Critic    -> accepts/rejects a result (JSON), with feedback for retry.
Synthesizer -> merges accepted results into a final answer.

JSON is extracted tolerantly so a model that wraps output in ``` fences still parses.
"""

from __future__ import annotations

import json
from typing import Any

from polyagent.core.agent import Agent
from polyagent.orchestration.types import Critique, TaskNode


def _extract_json(text: str) -> Any:
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        s = s.rsplit("```", 1)[0]
    return json.loads(s)


class Planner:
    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    async def plan(self, goal: str) -> list[TaskNode]:
        prompt = (
            "Break the goal into subtasks. Reply with ONLY a JSON array: "
            '[{"id":"t1","description":"...","deps":[]}].\n'
            f"Goal: {goal}"
        )
        resp = await self.agent.run(prompt)
        data = _extract_json(resp.content)
        return [TaskNode(**item) for item in data]


class Worker:
    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    async def execute(self, task: TaskNode) -> str:
        resp = await self.agent.run(task.description)
        return resp.content


class Critic:
    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    async def review(self, task: TaskNode, result: str) -> Critique:
        prompt = (
            "Evaluate the task result. Reply with ONLY JSON: "
            '{"accepted": true|false, "feedback": "..."}.\n'
            f"Task: {task.description}\nResult: {result}"
        )
        resp = await self.agent.run(prompt)
        return Critique(**_extract_json(resp.content))


class Synthesizer:
    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    async def synthesize(self, goal: str, tasks: list[TaskNode]) -> str:
        done = [t for t in tasks if t.status.value == "done" and t.result is not None]
        summary = "\n".join(f"- {t.id}: {t.result}" for t in done)
        prompt = (
            "Synthesize a final answer for the goal using these results.\n"
            f"Goal: {goal}\nResults:\n{summary}"
        )
        resp = await self.agent.run(prompt)
        return resp.content

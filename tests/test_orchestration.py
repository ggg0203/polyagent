"""Orchestrator: pipeline, DAG deps, critic retry, failure blocking."""

from __future__ import annotations

from polyagent.core.agent import Agent
from polyagent.core.types import AgentSpec
from polyagent.llm.client import LLMClient
from polyagent.llm.mock import MockProvider
from polyagent.llm.types import LLMResponse
from polyagent.orchestration import (
    Critic,
    Orchestrator,
    Planner,
    Synthesizer,
    TaskStatus,
    Worker,
)


def _agent(prov: MockProvider) -> Agent:
    return Agent(AgentSpec(name="a", role="x", model="mock"), LLMClient(prov))


def _resp(content: str) -> LLMResponse:
    return LLMResponse(content=content, model="mock")


TASKS_TWO = (
    '[{"id":"t1","description":"step one","deps":[]},'
    '{"id":"t2","description":"step two","deps":["t1"]}]'
)


async def test_planner_parses_task_list() -> None:
    prov = MockProvider(script=[_resp(TASKS_TWO)])
    planner = Planner(_agent(prov))
    tasks = await planner.plan("build app")
    assert len(tasks) == 2
    assert tasks[1].deps == ["t1"]


async def test_orchestrator_runs_full_pipeline() -> None:
    planner_prov = MockProvider(script=[_resp(TASKS_TWO)])
    worker_prov = MockProvider(script=[_resp("w1"), _resp("w2")])
    critic_prov = MockProvider(
        script=[
            _resp('{"accepted": true, "feedback": "ok"}'),
            _resp('{"accepted": true, "feedback": "ok"}'),
        ]
    )
    synth_prov = MockProvider(script=[_resp("FINAL ANSWER")])

    orch = Orchestrator(
        Planner(_agent(planner_prov)),
        Worker(_agent(worker_prov)),
        Critic(_agent(critic_prov)),
        Synthesizer(_agent(synth_prov)),
    )
    result = await orch.run("do something")

    assert result.answer == "FINAL ANSWER"
    assert all(t.status == TaskStatus.DONE for t in result.task_graph)
    assert len(result.task_graph) == 2
    # deps respected: t1 executed before t2
    assert worker_prov.calls[0].messages[-1].content == "step one"
    assert worker_prov.calls[1].messages[-1].content == "step two"
    assert result.total_attempts == 2


async def test_critic_rejection_triggers_retry() -> None:
    planner_prov = MockProvider(script=[_resp('[{"id":"t1","description":"d","deps":[]}]')])
    worker_prov = MockProvider(script=[_resp("bad"), _resp("good")])
    critic_prov = MockProvider(
        script=[
            _resp('{"accepted": false, "feedback": "redo"}'),
            _resp('{"accepted": true, "feedback": "ok"}'),
        ]
    )
    synth_prov = MockProvider(script=[_resp("done")])

    orch = Orchestrator(
        Planner(_agent(planner_prov)),
        Worker(_agent(worker_prov)),
        Critic(_agent(critic_prov)),
        Synthesizer(_agent(synth_prov)),
        max_review_retries=2,
    )
    result = await orch.run("x")
    task = result.task_graph[0]
    assert task.status == TaskStatus.DONE
    assert task.attempts == 2
    assert task.result == "good"


async def test_failed_task_blocks_dependents() -> None:
    planner_prov = MockProvider(script=[_resp(TASKS_TWO)])
    worker_prov = MockProvider(script=[_resp("a1"), _resp("a2"), _resp("a3")])
    critic_prov = MockProvider(
        script=[
            _resp('{"accepted": false, "feedback": "no"}'),
            _resp('{"accepted": false, "feedback": "no"}'),
            _resp('{"accepted": false, "feedback": "no"}'),
        ]
    )
    synth_prov = MockProvider(script=[_resp("partial")])

    orch = Orchestrator(
        Planner(_agent(planner_prov)),
        Worker(_agent(worker_prov)),
        Critic(_agent(critic_prov)),
        Synthesizer(_agent(synth_prov)),
        max_review_retries=2,
    )
    result = await orch.run("x")
    by_id = {t.id: t for t in result.task_graph}
    assert by_id["t1"].status == TaskStatus.FAILED
    assert by_id["t1"].attempts == 3
    # t2 never ran — blocked by failed t1
    assert by_id["t2"].status == TaskStatus.FAILED
    assert by_id["t2"].attempts == 0

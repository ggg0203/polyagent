"""Observability: tracer nesting, error marking, metrics, end-to-end trace + cost."""

from __future__ import annotations

import pytest

from polyagent.core.agent import Agent
from polyagent.core.types import AgentSpec, CostReport, Usage
from polyagent.llm.client import LLMClient
from polyagent.llm.middleware import CostAccountMiddleware
from polyagent.llm.mock import MockProvider
from polyagent.llm.types import LLMResponse
from polyagent.observability import Metrics, ObservabilityMiddleware, Tracer
from polyagent.orchestration import Critic, Orchestrator, Planner, Synthesizer, Worker

TASKS_TWO = (
    '[{"id":"t1","description":"step one","deps":[]},'
    '{"id":"t2","description":"step two","deps":["t1"]}]'
)


def _resp(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="deepseek-chat",
        usage=Usage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
    )


def _role(prov: MockProvider, tracer: Tracer, metrics: Metrics, cost: CostReport) -> Agent:
    client = LLMClient(
        prov,
        [ObservabilityMiddleware(tracer, metrics), CostAccountMiddleware(cost)],
    )
    return Agent(AgentSpec(name="r", role="x", model="deepseek-chat"), client)


def test_tracer_nested_spans_form_a_tree() -> None:
    tracer = Tracer()
    with tracer.span("root"):
        with tracer.span("child1"):
            pass
        with tracer.span("child2"), tracer.span("grandchild"):
            pass
    d = tracer.to_dict()
    assert len(d["spans"]) == 1
    root = d["spans"][0]
    assert root["name"] == "root"
    assert [c["name"] for c in root["children"]] == ["child1", "child2"]
    assert root["children"][1]["children"][0]["name"] == "grandchild"


def test_tracer_marks_error_and_reraises() -> None:
    tracer = Tracer()
    with pytest.raises(ValueError), tracer.span("boom"):
        raise ValueError("x")
    d = tracer.to_dict()
    assert d["spans"][0]["status"] == "error"
    assert "ValueError" in (d["spans"][0]["error"] or "")


def test_metrics_summary_aggregates() -> None:
    m = Metrics()
    m.inc("calls")
    m.inc("calls")
    m.observe("latency", 0.1)
    m.observe("latency", 0.3)
    s = m.summary()
    assert s["calls"] == 2
    assert s["latency.count"] == 2
    assert s["latency.max"] == 0.3


async def test_run_produces_trace_metrics_and_cost() -> None:
    tracer = Tracer()
    metrics = Metrics()
    cost = CostReport()

    planner = Planner(_role(MockProvider(script=[_resp(TASKS_TWO)]), tracer, metrics, cost))
    worker = Worker(_role(MockProvider(script=[_resp("w1"), _resp("w2")]), tracer, metrics, cost))
    critic = Critic(
        _role(
            MockProvider(
                script=[
                    _resp('{"accepted": true, "feedback": "ok"}'),
                    _resp('{"accepted": true, "feedback": "ok"}'),
                ]
            ),
            tracer,
            metrics,
            cost,
        )
    )
    synth = Synthesizer(_role(MockProvider(script=[_resp("ANSWER")]), tracer, metrics, cost))

    orch = Orchestrator(planner, worker, critic, synth, tracer=tracer, cost_report=cost)
    result = await orch.run("build app")

    # trace: one root (orchestrator.run) with plan/schedule/synth children
    d = tracer.to_dict()
    assert len(d["spans"]) == 1
    root = d["spans"][0]
    assert root["name"] == "orchestrator.run"
    child_names = [c["name"] for c in root["children"]]
    assert "planner.plan" in child_names
    assert "synthesizer.synthesize" in child_names

    # metrics: every LLM call was counted (planner1 + worker2 + critic2 + synth1 = 6)
    assert metrics.summary()["llm.calls"] == 6
    assert metrics.summary()["llm.tokens"] == 60

    # cost: deepseek-chat pricing applied across all calls
    assert cost.estimated_cost_usd > 0
    assert result.answer == "ANSWER"

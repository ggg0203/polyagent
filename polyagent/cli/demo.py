"""Demo orchestrator built from scripted Mock providers (fully offline).

Lets ``polyagent run`` exercise the whole Plan -> Workers -> Critic -> Synthesize
pipeline with no API key. The planner returns a fixed 2-task DAG; the worker
echoes; the critic always accepts; the synthesizer returns a placeholder.
"""

from __future__ import annotations

from polyagent.core.agent import Agent
from polyagent.core.types import AgentSpec, CostReport
from polyagent.llm.client import LLMClient
from polyagent.llm.mock import MockProvider
from polyagent.llm.types import LLMResponse
from polyagent.observability.tracer import Tracer
from polyagent.orchestration import Critic, Orchestrator, Planner, Synthesizer, Worker

DEFAULT_TASKS = (
    '[{"id":"t1","description":"analyze the goal and gather context","deps":[]},'
    '{"id":"t2","description":"draft a solution from the analysis","deps":["t1"]}]'
)


def _agent(prov: MockProvider) -> Agent:
    return Agent(AgentSpec(name="demo", role="x", model="mock"), LLMClient(prov))


def build_demo_orchestrator() -> tuple[Orchestrator, Tracer, CostReport]:
    accept = LLMResponse(content='{"accepted": true, "feedback": "ok"}', model="mock")
    synth = LLMResponse(content="[demo] synthesized final answer", model="mock")
    planner_resp = LLMResponse(content=DEFAULT_TASKS, model="mock")
    planner = Planner(_agent(MockProvider(script=[planner_resp])))
    worker = Worker(_agent(MockProvider()))
    critic = Critic(_agent(MockProvider(default=accept)))
    synthesizer = Synthesizer(_agent(MockProvider(default=synth)))
    tracer = Tracer()
    cost = CostReport()
    orch = Orchestrator(planner, worker, critic, synthesizer, tracer=tracer, cost_report=cost)
    return orch, tracer, cost


def build_deepseek_orchestrator() -> tuple[Orchestrator, Tracer, CostReport]:
    """Real-LLM orchestrator: every role uses DeepSeek via settings from .env."""
    from polyagent.config import get_settings
    from polyagent.llm.deepseek import DeepSeekProvider

    s = get_settings()
    if not s.api_key:
        msg = "DEEPSEEK_API_KEY not set; add it to .env (see .env.example)."
        raise ValueError(msg)

    tracer = Tracer()
    cost = CostReport()

    def _client() -> LLMClient:
        from polyagent.llm.middleware import CostAccountMiddleware
        from polyagent.observability import ObservabilityMiddleware

        return LLMClient(
            DeepSeekProvider(api_key=s.api_key, base_url=s.base_url, model=s.model),
            [ObservabilityMiddleware(tracer), CostAccountMiddleware(cost)],
        )

    def _agent(role: str, system_prompt: str) -> Agent:
        return Agent(
            AgentSpec(name=role, role=role, model=s.model, system_prompt=system_prompt),
            _client(),
        )

    planner = Planner(
        _agent(
            "planner",
            "You decompose a goal into subtasks. Reply ONLY with a JSON array: "
            '[{"id":"t1","description":"...","deps":[]}].',
        )
    )
    worker = Worker(_agent("worker", "You execute a subtask and return its result."))
    critic = Critic(
        _agent(
            "critic",
            "You review a task result. Reply ONLY with JSON: "
            '{"accepted": true|false, "feedback": "..."}.',
        )
    )
    synthesizer = Synthesizer(
        _agent("synthesizer", "You synthesize a final answer from subtask results.")
    )
    orch = Orchestrator(planner, worker, critic, synthesizer, tracer=tracer, cost_report=cost)
    return orch, tracer, cost

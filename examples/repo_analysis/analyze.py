"""Code repository analysis showcase.

Demonstrates PolyAgent applied to code-repo analysis: a Planner decomposes
"analyze repo" into inventory / entrypoints / tests / smells / report tasks;
Workers carry grep_files + read_file tools; a Critic reviews each step; a
Synthesizer writes the report.

Default run uses Mock providers (offline — prints a placeholder report and
exercises the full Plan -> Workers -> Critic -> Synthesizer pipeline).
A real analysis needs a live LLM (deepseek) and the worker tools actually
reading the repo at ``--repo``.
"""

from __future__ import annotations

import asyncio

import typer

from polyagent.core.agent import Agent
from polyagent.core.types import AgentSpec, CostReport
from polyagent.llm.client import LLMClient
from polyagent.llm.mock import MockProvider
from polyagent.llm.types import LLMResponse
from polyagent.observability.tracer import Tracer
from polyagent.orchestration import Critic, Orchestrator, Planner, Synthesizer, Worker
from polyagent.tools import with_builtins

PLAN = (
    '[{"id":"inv","description":"list repo files and directory structure","deps":[]},'
    '{"id":"entry","description":"identify entry points and main modules","deps":["inv"]},'
    '{"id":"tests","description":"assess test coverage and quality","deps":["inv"]},'
    '{"id":"smells","description":"flag code smells and improvement opportunities",'
    '"deps":["entry"]},'
    '{"id":"report","description":"synthesize a written analysis report",'
    '"deps":["entry","tests","smells"]}]'
)

app = typer.Typer(add_completion=False)


def _agent(role: str, system_prompt: str, prov: MockProvider, with_tools: bool = False) -> Agent:
    return Agent(
        AgentSpec(name=role, role=role, model="mock", system_prompt=system_prompt),
        LLMClient(prov),
        tools=with_builtins() if with_tools else None,
    )


def build_orchestrator(repo: str) -> tuple[Orchestrator, Tracer, CostReport]:
    accept = LLMResponse(content='{"accepted": true, "feedback": "ok"}', model="mock")
    report = LLMResponse(content="[demo] repo analysis report (mock)", model="mock")
    planner = Planner(
        _agent(
            "planner",
            "You decompose a code-analysis goal into subtasks as JSON.",
            MockProvider(script=[LLMResponse(content=PLAN, model="mock")]),
        )
    )
    worker = Worker(
        _agent(
            "worker",
            "You analyze code using the provided tools (grep_files, read_file).",
            MockProvider(),
            with_tools=True,
        )
    )
    critic = Critic(
        _agent("critic", "You review analysis steps for correctness.", MockProvider(default=accept))
    )
    synth = Synthesizer(
        _agent(
            "synthesizer",
            "You write a clear analysis report.",
            MockProvider(default=report),
        )
    )
    tracer = Tracer()
    cost = CostReport()
    orch = Orchestrator(planner, worker, critic, synth, tracer=tracer, cost_report=cost)
    return orch, tracer, cost


@app.command()
def analyze(
    repo: str = typer.Argument(".", help="Path to the repo to analyze."),
    provider: str = typer.Option("mock", help="mock | deepseek (deepseek needs DEEPSEEK_API_KEY)."),
) -> None:
    """Run the repo-analysis pipeline."""
    if provider != "mock":
        typer.echo("showcase wires only 'mock' for now; deepseek TBD.", err=True)
        raise typer.Exit(1)
    orch, tracer, cost = build_orchestrator(repo)
    result = asyncio.run(orch.run(f"Analyze the repository at {repo}"))
    typer.echo("=== Repo Analysis Report ===")
    typer.echo(result.answer)
    typer.echo(
        f"\nTasks: {len(result.task_graph)} | Attempts: {result.total_attempts} | "
        f"Trace roots: {len(tracer.roots)}"
    )


if __name__ == "__main__":  # pragma: no cover
    app()

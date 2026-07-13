"""Eval: scorers, runner, default dataset, CLI eval command."""

from __future__ import annotations

from polyagent.core.agent import Agent
from polyagent.core.types import AgentSpec
from polyagent.eval import (
    ContainsScorer,
    Dataset,
    EvalRunner,
    ExactMatchScorer,
)
from polyagent.llm.client import LLMClient
from polyagent.llm.mock import MockProvider


def test_exact_match_scorer() -> None:
    from polyagent.eval import EvalCase

    case = EvalCase(id="x", input="hi", expected="hello")
    assert ExactMatchScorer().score(case, "hello").passed is True
    assert ExactMatchScorer().score(case, "hello ").passed is True  # trimmed
    assert ExactMatchScorer().score(case, "world").passed is False


def test_contains_scorer() -> None:
    from polyagent.eval import EvalCase

    case = EvalCase(id="x", input="hi", expected="secret")
    assert ContainsScorer().score(case, "the secret is here").passed is True
    assert ContainsScorer().score(case, "nothing here").passed is False


def test_default_dataset_has_three_cases() -> None:
    ds = Dataset.default()
    assert len(ds) == 3
    assert {c.id for c in ds.cases} == {"c1", "c2", "c3"}


async def test_runner_default_dataset_two_of_three_pass() -> None:
    agent = Agent(AgentSpec(name="e", role="worker", model="mock"), LLMClient(MockProvider()))

    async def subject(inp: str) -> str:
        return (await agent.run(inp)).content

    report = await EvalRunner(subject, ContainsScorer()).run(Dataset.default())
    assert report.n == 3
    assert report.passed == 2
    by_id = {r.case_id: r for r in report.results}
    assert by_id["c1"].passed is True
    assert by_id["c2"].passed is True
    assert by_id["c3"].passed is False
    assert 0 < report.pass_rate < 1


def test_eval_command_outputs_report() -> None:
    from typer.testing import CliRunner

    from polyagent.cli import app

    result = CliRunner().invoke(app, ["eval"])
    assert result.exit_code == 0
    assert "Eval:" in result.stdout
    assert "2/3" in result.stdout
    assert "FAIL" in result.stdout
    assert "c3" in result.stdout

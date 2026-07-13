"""EvalRunner — run a subject over a dataset, score each, aggregate into a report.

``subject`` is any ``async (input: str) -> str`` callable — an Agent, an
Orchestrator wrapper, or a plain function. This keeps the runner decoupled from
whatever it is evaluating.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from polyagent.eval.dataset import Dataset
from polyagent.eval.scorers import Scorer
from polyagent.eval.types import EvalReport, EvalResult

Subject = Callable[[str], Awaitable[str]]


class EvalRunner:
    def __init__(self, subject: Subject, scorer: Scorer) -> None:
        self.subject = subject
        self.scorer = scorer

    async def run(self, dataset: Dataset) -> EvalReport:
        results: list[EvalResult] = []
        for case in dataset.cases:
            output = await self.subject(case.input)
            results.append(self.scorer.score(case, output))
        return EvalReport.build(results)

"""Dataset — a list of eval cases, with a tiny default set for regression."""

from __future__ import annotations

from polyagent.eval.types import EvalCase


class Dataset:
    def __init__(self, cases: list[EvalCase] | None = None) -> None:
        self.cases: list[EvalCase] = list(cases) if cases else []

    @classmethod
    def default(cls) -> Dataset:
        return cls(
            [
                EvalCase(id="c1", input="hello", expected="hello"),
                EvalCase(id="c2", input="world", expected="world"),
                EvalCase(id="c3", input="probe", expected="MISSING"),
            ]
        )

    def __len__(self) -> int:
        return len(self.cases)

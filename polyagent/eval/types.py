"""Eval types: cases, results, report."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EvalCase(BaseModel):
    id: str
    input: str
    expected: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalResult(BaseModel):
    case_id: str
    passed: bool
    score: float
    output: str
    detail: str = ""


class EvalReport(BaseModel):
    results: list[EvalResult]
    n: int = 0
    passed: int = 0
    pass_rate: float = 0.0
    avg_score: float = 0.0

    @classmethod
    def build(cls, results: list[EvalResult]) -> EvalReport:
        n = len(results)
        passed = sum(1 for r in results if r.passed)
        return cls(
            results=results,
            n=n,
            passed=passed,
            pass_rate=(passed / n) if n else 0.0,
            avg_score=(sum(r.score for r in results) / n) if n else 0.0,
        )

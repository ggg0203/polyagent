"""Scorers — compare actual output to a case's expected value.

Pluggable: ExactMatchScorer / ContainsScorer are deterministic and offline.
An LLMJudgeScorer (asks a model to grade) can be added later behind the same
protocol; the runner doesn't care which scorer it gets.
"""

from __future__ import annotations

from typing import Any, Protocol

from polyagent.eval.types import EvalCase, EvalResult


class Scorer(Protocol):
    def score(self, case: EvalCase, output: str) -> EvalResult: ...


class ExactMatchScorer:
    def score(self, case: EvalCase, output: str) -> EvalResult:
        passed = output.strip() == case.expected.strip()
        return EvalResult(
            case_id=case.id,
            passed=passed,
            score=1.0 if passed else 0.0,
            output=output,
            detail="exact match",
        )


class ContainsScorer:
    def score(self, case: EvalCase, output: str) -> EvalResult:
        passed = case.expected in output
        return EvalResult(
            case_id=case.id,
            passed=passed,
            score=1.0 if passed else 0.0,
            output=output,
            detail="contains expected substring",
        )


def _extract_json(text: str) -> Any:
    import json

    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        s = s.rsplit("```", 1)[0]
    return json.loads(s)


class LLMJudgeScorer:
    """Grade output vs expected using an LLM (DeepSeek) as a judge.

    Synchronous (uses ``httpx.post``); returns score 1.0/0.0 based on the model's
    JSON verdict ``{"score": 0|1, "reason": "..."}``. On any error returns 0.0.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    def score(self, case: EvalCase, output: str) -> EvalResult:
        import httpx

        prompt = (
            "Rate whether the actual answer satisfies the expected criteria. "
            'Reply ONLY JSON: {"score": 0|1, "reason": "..."}.\n'
            f"Input: {case.input}\nExpected: {case.expected}\nActual: {output}"
        )
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            data = _extract_json(content)
            passed = bool(data.get("score", 0))
            return EvalResult(
                case_id=case.id,
                passed=passed,
                score=1.0 if passed else 0.0,
                output=output,
                detail=f"llm judge: {data.get('reason', '')}",
            )
        except Exception as exc:  # noqa: BLE001
            return EvalResult(
                case_id=case.id,
                passed=False,
                score=0.0,
                output=output,
                detail=f"llm judge error: {exc}",
            )

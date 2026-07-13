"""RunReport — bundles trace, metrics, cost, latency for one run."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from polyagent.core.types import CostReport


class RunReport(BaseModel):
    answer: str = ""
    trace: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    cost: CostReport = Field(default_factory=CostReport)
    latency: float = 0.0

    @classmethod
    def build(
        cls,
        *,
        answer: str,
        trace: dict[str, Any],
        metrics: dict[str, Any],
        cost: CostReport,
        latency: float,
    ) -> RunReport:
        return cls(answer=answer, trace=trace, metrics=metrics, cost=cost, latency=latency)

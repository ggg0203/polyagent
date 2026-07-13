"""Orchestrator — the multi-agent pipeline scheduler.

Flow: Planner -> Workers(parallel, semaphore-bounded) -> Critic (review, retry on
reject) -> Synthesizer. Tasks form a DAG; a task runs only after its deps are DONE.
A task whose dep FAILED is itself marked FAILED (no point executing on broken input).

Reliability middleware (retry/fallback/cost) lives on each role's LLMClient (M1).
An optional ``tracer`` emits spans around plan / schedule / synthesise / each task
and its worker+critic sub-steps; ``ObservabilityMiddleware`` on the clients then
nests ``llm.chat`` spans automatically under the active span.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import nullcontext
from typing import Any

from polyagent.core.types import CostReport
from polyagent.observability.tracer import Tracer
from polyagent.orchestration.roles import Critic, Planner, Synthesizer, Worker
from polyagent.orchestration.types import RunResult, TaskNode, TaskStatus


class Orchestrator:
    def __init__(
        self,
        planner: Planner,
        worker: Worker,
        critic: Critic,
        synthesizer: Synthesizer,
        *,
        max_concurrency: int = 4,
        max_review_retries: int = 2,
        cost_report: CostReport | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self.planner = planner
        self.worker = worker
        self.critic = critic
        self.synthesizer = synthesizer
        self.max_concurrency = max_concurrency
        self.max_review_retries = max_review_retries
        self.cost_report = cost_report
        self.tracer = tracer

    def _span(self, name: str, **attrs: Any) -> Any:
        if self.tracer is not None:
            return self.tracer.span(name, **attrs)
        return nullcontext()

    async def run(self, goal: str) -> RunResult:
        with self._span("orchestrator.run", goal=goal):
            start = time.monotonic()
            with self._span("planner.plan"):
                tasks = await self.planner.plan(goal)
            with self._span("schedule"):
                await self._schedule(tasks)
            with self._span("synthesizer.synthesize"):
                answer = await self.synthesizer.synthesize(goal, tasks)
            latency = time.monotonic() - start
            total_attempts = sum(t.attempts for t in tasks)
            return RunResult(
                answer=answer,
                task_graph=tasks,
                latency=latency,
                total_attempts=total_attempts,
                estimated_cost_usd=(
                    self.cost_report.estimated_cost_usd if self.cost_report else 0.0
                ),
            )

    async def _schedule(self, tasks: list[TaskNode]) -> None:
        sem = asyncio.Semaphore(self.max_concurrency)
        processed: set[str] = set()
        completed: set[str] = set()

        while len(processed) < len(tasks):
            ready = [
                t
                for t in tasks
                if t.id not in processed
                and t.status == TaskStatus.PENDING
                and all(d in completed for d in t.deps)
            ]
            if not ready:
                for t in tasks:
                    if t.id not in processed:
                        t.status = TaskStatus.FAILED
                        processed.add(t.id)
                break

            await asyncio.gather(*[self._run_task(sem, t) for t in ready])
            for t in ready:
                processed.add(t.id)
                if t.status == TaskStatus.DONE:
                    completed.add(t.id)

    async def _run_task(self, sem: asyncio.Semaphore, task: TaskNode) -> None:
        async with sem:
            with self._span("task", task_id=task.id, description=task.description):
                task.status = TaskStatus.RUNNING
                last = ""
                for attempt in range(self.max_review_retries + 1):
                    with self._span("worker.execute", attempt=attempt):
                        last = await self.worker.execute(task)
                    with self._span("critic.review", attempt=attempt):
                        critique = await self.critic.review(task, last)
                    if critique.accepted:
                        task.result = last
                        task.status = TaskStatus.DONE
                        task.attempts = attempt + 1
                        return
                task.result = last
                task.status = TaskStatus.FAILED
                task.attempts = self.max_review_retries + 1

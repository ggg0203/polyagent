"""Orchestration types: task graph, statuses, critique, run result."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class TaskNode(BaseModel):
    id: str
    description: str
    deps: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: str | None = None
    attempts: int = 0


class Critique(BaseModel):
    accepted: bool
    feedback: str = ""


class RunResult(BaseModel):
    answer: str
    task_graph: list[TaskNode]
    latency: float = 0.0
    total_attempts: int = 0
    estimated_cost_usd: float = 0.0

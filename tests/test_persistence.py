"""Persistence: RunStore save / list / get on sqlite."""

from __future__ import annotations

from polyagent.orchestration.types import RunResult, TaskNode, TaskStatus
from polyagent.persistence import RunStore


def _result() -> RunResult:
    return RunResult(
        answer="final answer",
        task_graph=[
            TaskNode(
                id="t1",
                description="do thing",
                deps=[],
                status=TaskStatus.DONE,
                result="done output",
                attempts=1,
            )
        ],
        latency=0.5,
        total_attempts=1,
        estimated_cost_usd=0.001,
    )


def test_save_then_list_and_get(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "test.db"
    store = RunStore(str(db))
    run_id = store.save(goal="my goal", result=_result(), trace={"spans": [{"name": "root"}]})
    store.close()
    assert len(run_id) == 12

    store2 = RunStore(str(db))
    rows = store2.list()
    assert len(rows) == 1
    assert rows[0]["goal"] == "my goal"
    assert rows[0]["cost_usd"] == 0.001

    data = store2.get(run_id)
    assert data is not None
    assert data["run"]["answer"] == "final answer"
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["id"] == "t1"
    assert data["tasks"][0]["status"] == "done"
    assert data["trace"]["spans"][0]["name"] == "root"
    store2.close()


def test_get_missing_returns_none(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = RunStore(str(tmp_path / "x.db"))
    assert store.get("nonexistent") is None
    store.close()


def test_multiple_runs_listed_newest_first(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = RunStore(str(tmp_path / "m.db"))
    store.save(goal="first", result=_result(), trace={})
    store.save(goal="second", result=_result(), trace={})
    rows = store.list()
    assert [r["goal"] for r in rows] == ["second", "first"]
    store.close()

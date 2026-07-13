"""Sandbox: PathGuard + DockerSandbox (skipped without docker)."""

from __future__ import annotations

import shutil

import pytest

from polyagent.tools import DockerSandbox, PathGuard, PythonExecute


def test_path_guard_allows_inside_root(tmp_path) -> None:  # type: ignore[no-untyped-def]
    guard = PathGuard([str(tmp_path)])
    ok, _ = guard.check(str(tmp_path / "sub" / "file.txt"))
    assert ok is True


def test_path_guard_rejects_outside(tmp_path) -> None:  # type: ignore[no-untyped-def]
    guard = PathGuard([str(tmp_path)])
    ok, _ = guard.check("/etc/passwd")
    assert ok is False


async def test_python_execute_subprocess_default() -> None:
    tool = PythonExecute()
    result = await tool.call({"code": "print(2 + 2)"})
    assert result.error is False
    assert "4" in result.output


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not available")
async def test_docker_sandbox_runs_code() -> None:
    sandbox = DockerSandbox(image="python:3.12-slim", timeout=120)
    result = await sandbox.run("print('hello from container')")
    assert result.error is False
    assert "hello from container" in result.output


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not available")
async def test_python_execute_with_docker() -> None:
    tool = PythonExecute(sandbox=DockerSandbox(image="python:3.12-slim", timeout=120))
    result = await tool.call({"code": "print(2 + 2)"})
    assert result.error is False
    assert "4" in result.output

"""CLI: version / run / chat / eval via typer's CliRunner."""

from __future__ import annotations

from typer.testing import CliRunner

from polyagent.cli import app

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.4" in result.stdout


def test_run_command_executes_pipeline() -> None:
    result = runner.invoke(app, ["run", "build a web app", "--no-persist"])
    assert result.exit_code == 0
    assert "Answer:" in result.stdout
    assert "t1" in result.stdout
    assert "done" in result.stdout
    assert "Trace roots: 1" in result.stdout


def test_run_rejects_unknown_provider() -> None:
    result = runner.invoke(app, ["run", "x", "--provider", "unknown"])
    assert result.exit_code != 0


def test_eval_runs_dataset() -> None:
    result = runner.invoke(app, ["eval"])
    assert result.exit_code == 0
    assert "Eval:" in result.stdout
    assert "2/3" in result.stdout


def test_shell_shows_help() -> None:
    """shell command should be registered and show relevant flags."""
    result = runner.invoke(app, ["shell", "--help"])
    assert result.exit_code == 0
    assert "stream" in result.stdout or "PolyAgent" in result.stdout


def test_run_persist_and_list() -> None:
    """run with --persist should save to db and `runs` should list it."""
    result = runner.invoke(app, ["run", "test persist", "--persist"])
    assert result.exit_code == 0
    assert "Run ID:" in result.stdout

    result2 = runner.invoke(app, ["runs"])
    assert result2.exit_code == 0
    assert "test persist" in result2.stdout

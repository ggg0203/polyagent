"""Smoke tests: ensure the package and all submodules import cleanly.

These run offline with no network and no API keys required.
"""

from __future__ import annotations

import importlib

import polyagent


def test_version_exposed() -> None:
    assert polyagent.__version__ == "0.1.1"


def test_all_subpackages_importable() -> None:
    modules = [
        "polyagent.core",
        "polyagent.llm",
        "polyagent.tools",
        "polyagent.memory",
        "polyagent.rag",
        "polyagent.orchestration",
        "polyagent.observability",
        "polyagent.eval",
        "polyagent.cli",
    ]
    for name in modules:
        assert importlib.import_module(name) is not None


def test_cli_app_is_a_typer() -> None:
    import typer

    from polyagent.cli import app

    assert isinstance(app, typer.Typer)

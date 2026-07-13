"""ToolRegistry — name -> Tool, with schema export + a builtin default set."""

from __future__ import annotations

from typing import Any

from polyagent.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            msg = f"tool already registered: {tool.name}"
            raise ValueError(msg)
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            msg = f"unknown tool: {name}"
            raise KeyError(msg)
        return self._tools[name]

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools


def with_builtins() -> ToolRegistry:
    """A registry pre-loaded with the framework's builtin tools."""
    from polyagent.tools.builtins import (
        GrepFiles,
        HttpRequest,
        MarketplaceInstall,
        MarketplaceSearch,
        PythonExecute,
        ReadFile,
        SkillHubInstall,
        SkillHubInstallFromPrompt,
        SkillHubList,
        SkillHubSearch,
        WebSearch,
        WriteFile,
    )

    reg = ToolRegistry()
    for tool in (
        PythonExecute(),
        ReadFile(),
        WriteFile(),
        HttpRequest(),
        GrepFiles(),
        WebSearch(),
        MarketplaceSearch(),
        MarketplaceInstall(),
        SkillHubSearch(),
        SkillHubInstall(),
        SkillHubInstallFromPrompt(),
        SkillHubList(),
    ):
        reg.register(tool)
    return reg

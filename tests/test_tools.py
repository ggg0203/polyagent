"""Tools: schema auto-generation, registry, builtins, and the Agent tool loop."""

from __future__ import annotations

from pydantic import BaseModel

from polyagent.core.agent import Agent
from polyagent.core.types import AgentSpec, Role, ToolCall
from polyagent.llm.client import LLMClient
from polyagent.llm.mock import MockProvider
from polyagent.llm.types import LLMResponse
from polyagent.tools import (
    GrepFiles,
    MarketplaceInstall,
    MarketplaceSearch,
    PythonExecute,
    ReadFile,
    SkillHubInstallFromPrompt,
    SkillHubList,
    SkillHubSearch,
    Tool,
    ToolRegistry,
    ToolResult,
    WebSearch,
    WriteFile,
    with_builtins,
)

# --- a tiny custom tool for schema/registry tests ------------------------- #


class _EchoArgs(BaseModel):
    text: str


class _EchoTool(Tool):
    name = "echo"
    description = "echo the text back"
    args_model = _EchoArgs

    async def run(self, args: _EchoArgs) -> ToolResult:
        return ToolResult(output=args.text)


# --- schema ---------------------------------------------------------------- #


def test_schema_auto_generated_from_pydantic() -> None:
    schema = _EchoTool.schema()
    assert schema["type"] == "function"
    fn = schema["function"]
    assert fn["name"] == "echo"
    assert fn["description"] == "echo the text back"
    params = fn["parameters"]
    assert "text" in params["properties"]
    assert "text" in params["required"]


def test_builtin_tool_schemas_have_required_fields() -> None:
    schema = PythonExecute.schema()
    assert schema["function"]["name"] == "python_execute"
    assert "code" in schema["function"]["parameters"]["properties"]


# --- registry -------------------------------------------------------------- #


def test_registry_register_get_and_lookup() -> None:
    reg = ToolRegistry()
    tool = reg.register(_EchoTool())
    assert reg.get("echo") is tool
    assert "echo" in reg
    assert len(reg) == 1
    schemas = reg.schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "echo"


def test_registry_rejects_duplicate() -> None:
    import pytest

    reg = ToolRegistry()
    reg.register(_EchoTool())
    with pytest.raises(ValueError):
        reg.register(_EchoTool())


def test_with_builtins_registers_twelve_tools() -> None:
    reg = with_builtins()
    assert set(reg.names()) == {
        "python_execute",
        "read_file",
        "write_file",
        "http_request",
        "grep_files",
        "web_search",
        "marketplace_search",
        "marketplace_install",
        "skillhub_search",
        "skillhub_install",
        "skillhub_install_from_prompt",
        "skillhub_list",
    }


async def test_marketplace_search_returns_results() -> None:
    """marketplace_search should find skills by keyword."""
    result = await MarketplaceSearch().call({"query": "weather"})
    assert result.error is False
    assert "weather" in result.output


async def test_marketplace_search_no_match() -> None:
    """marketplace_search with no match should list all available."""
    result = await MarketplaceSearch().call({"query": "zzz_nonexistent_xyz"})
    assert result.error is False
    assert "Available skills" in result.output


async def test_marketplace_install_unknown() -> None:
    """marketplace_install on unknown skill should fail."""
    result = await MarketplaceInstall().call({"name": "nonexistent_skill"})
    assert result.error is True
    assert "unknown" in result.output


async def test_marketplace_install_and_uninstall() -> None:
    """Installing a skill should succeed; uninstalling should remove it."""
    import shutil
    from pathlib import Path

    from polyagent.skills import install_builtin, uninstall

    skills_dir = Path.home() / ".polyagent" / "skills"
    if skills_dir.exists():
        shutil.rmtree(skills_dir)

    ok, msg = install_builtin("weather")
    assert ok, msg
    assert "installed" in msg

    py = skills_dir / "weather_skill.py"
    assert py.is_file(), f"expected skill file: {py}"

    ok2, msg2 = uninstall("weather_skill")
    assert ok2, msg2
    assert not py.exists()


async def test_skillhub_search_handles_offline() -> None:
    """skillhub_search should handle API failures gracefully."""
    result = await SkillHubSearch().call({"query": "python"})
    # Network might be down — verify the tool doesn't crash
    assert isinstance(result.output, str)


async def test_skillhub_list_empty() -> None:
    """skillhub_list with no installed skills should return meaningful message."""
    import shutil
    from pathlib import Path
    from polyagent.tools.builtins import SKILLHUB_SKILLS_DIR

    if SKILLHUB_SKILLS_DIR.exists():
        shutil.rmtree(SKILLHUB_SKILLS_DIR)
    result = await SkillHubList().call({})
    assert result.error is False
    assert "No" in result.output


async def test_skillhub_search_api_parsing() -> None:
    """Test the search API parsing function various response shapes."""
    import json as _json
    from unittest.mock import patch
    from httpx import Response
    from polyagent.tools.builtins import _skillhub_search_api

    def _resp(data) -> Response:
        return Response(200, text=_json.dumps(data))

    # Mock a valid JSON response
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = _resp({
            "results": [{"name": "Test Skill", "slug": "test-skill", "description": "A test"}]
        })
        results = await _skillhub_search_api("test")
        assert len(results) == 1
        assert results[0]["name"] == "Test Skill"

    # Mock empty response
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = _resp({"results": []})
        results = await _skillhub_search_api("empty")
        assert len(results) == 0

    # Mock HTTP error
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = Response(500)
        results = await _skillhub_search_api("error")
        assert len(results) == 0

    # Mock list response (some APIs return a list directly)
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = _resp([
            {"name": "Direct List Skill"}
        ])
        results = await _skillhub_search_api("direct")
        assert len(results) == 1


async def test_skillhub_download_handles_errors() -> None:
    """SkillHub download should handle missing skills gracefully."""
    import shutil
    from pathlib import Path
    from polyagent.tools.builtins import SKILLHUB_SKILLS_DIR, _skillhub_download_skill

    if SKILLHUB_SKILLS_DIR.exists():
        shutil.rmtree(SKILLHUB_SKILLS_DIR)

    ok, msg = await _skillhub_download_skill("nonexistent-skill-xyz", SKILLHUB_SKILLS_DIR / "test")
    assert not ok


def test_skillhub_parse_search_result() -> None:
    """SkillHub result parser should handle various shapes."""
    from polyagent.tools.builtins import _skillhub_parse_search_result

    # Full result
    r1 = _skillhub_parse_search_result({
        "name": "PDF Helper",
        "slug": "pdf-helper",
        "description": "Help process PDF files",
        "tags": ["pdf", "document"],
        "author": "Tencent",
    })
    assert "PDF Helper" in r1
    assert "pdf-helper" in r1

    # Minimal result
    r2 = _skillhub_parse_search_result({"name": "test"})
    assert "test" in r2

    # Empty
    r3 = _skillhub_parse_search_result({})
    assert r3 is not None


def test_skillhub_slug_extraction_from_prompt() -> None:
    """_extract_skillhub_slug should parse official installation prompts."""
    from polyagent.tools.builtins import _extract_skillhub_slug

    # Chinese install pattern
    slug = _extract_skillhub_slug("请根据 https://skillhub.cn/install/skillhub.md，安装 pdf-image-text-extractor。")
    assert slug == "pdf-image-text-extractor"

    # English install pattern
    slug = _extract_skillhub_slug("Please install pdf-image-text-extractor from SkillHub.")
    assert slug == "pdf-image-text-extractor"

    # URL pattern
    slug = _extract_skillhub_slug("See https://skillhub.cn/install/pdf-helper.md")
    assert slug == "pdf-helper"

    # No slug
    slug = _extract_skillhub_slug("Hello, how are you?")
    assert slug is None


async def test_skillhub_install_from_prompt_no_slug() -> None:
    """skillhub_install_from_prompt should fail gracefully without a slug."""
    result = await SkillHubInstallFromPrompt().call({"prompt": "hello world"})
    assert result.error is True
    assert "Could not find" in result.output


async def test_web_search_returns_results() -> None:
    """WebSearch should handle connect/offline gracefully and not crash."""
    result = await WebSearch().call(
        {"query": "Python programming language", "max_results": 2}
    )
    # Verify the tool executes without crash regardless of network status.
    assert result is not None
    assert isinstance(result.output, str)
    # If network is available, we expect search results; otherwise a network error message.
    if "failed" in result.output:
        assert result.error is True


async def test_web_search_parses_html() -> None:
    """Verify HTML parsing logic with a mocked Bing response."""
    from unittest.mock import AsyncMock, patch

    from httpx import Response

    fake_html = """<html><body>
<li class="b_algo">
<h2 class=""><a href="https://python.org">Python Official Site</a></h2>
<p>Python is a high-level programming language</p>
</li>
</body></html>"""

    mock_get = AsyncMock(return_value=Response(200, text=fake_html))
    with patch("httpx.AsyncClient.get", mock_get):
        result = await WebSearch().call({"query": "python", "max_results": 3})
    assert result.error is False
    assert "Python Official Site" in result.output
    assert "high-level programming language" in result.output


async def test_web_search_engine_switch() -> None:
    """Verify engine parameter routing works."""
    from unittest.mock import AsyncMock, patch

    from httpx import Response

    # Test unknown engine returns error
    result = await WebSearch().call({"query": "test", "engine": "nonexistent"})
    assert result.error is True
    assert "Unknown engine" in result.output

    # Test engine parameter is accepted (will fail on network, not on validation)
    fake_html = """<html><body>
<li class="b_algo"><h2 class=""><a href="http://x.com">X</a></h2><p>test</p></li>
</body></html>"""
    mock_get = AsyncMock(return_value=Response(200, text=fake_html))
    with patch("httpx.AsyncClient.get", mock_get):
        result = await WebSearch().call({"query": "test", "engine": "bing", "max_results": 1})
    assert result.error is False


# --- builtins behaviour ---------------------------------------------------- #


async def test_python_execute_returns_stdout() -> None:
    result = await PythonExecute().call({"code": "print(2 + 2)"})
    assert result.error is False
    assert "4" in result.output


async def test_python_execute_reports_error() -> None:
    result = await PythonExecute().call({"code": "raise ValueError('boom')"})
    assert result.error is True
    assert "boom" in result.output


async def test_read_write_file_roundtrip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "note.txt"
    wf = WriteFile()
    r = await wf.call({"path": str(path), "content": "hello world"})
    assert r.error is False

    rf = ReadFile()
    r2 = await rf.call({"path": str(path)})
    assert r2.output == "hello world"


async def test_grep_files_finds_pattern(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "a.py").write_text("import os\nTODO: fix this\n", encoding="utf-8")
    result = await GrepFiles().call({"directory": str(tmp_path), "pattern": "TODO"})
    assert "TODO: fix this" in result.output


def test_invalid_args_returned_as_error_result() -> None:
    import asyncio

    async def _go() -> ToolResult:
        return await PythonExecute().call({"code": 123})  # type: ignore[arg-type]

    result = asyncio.run(_go())
    assert result.error is True


# --- Agent tool loop ------------------------------------------------------- #


async def test_agent_executes_tool_then_finishes() -> None:
    call = ToolCall(id="c1", name="python_execute", arguments='{"code": "print(2+2)"}')
    first = LLMResponse(content="", model="mock", tool_calls=[call])
    final = LLMResponse(content="the answer is 4", model="mock")
    prov = MockProvider(script=[first, final])
    agent = Agent(
        AgentSpec(name="t", role="worker", model="mock"),
        LLMClient(prov),
        tools=with_builtins(),
    )
    resp = await agent.run("compute 2+2")
    assert resp.content == "the answer is 4"

    # the second LLM request must carry the tool result as a tool message
    second_req = prov.calls[1]
    tool_msgs = [m for m in second_req.messages if m.role == Role.TOOL]
    assert len(tool_msgs) == 1
    assert "4" in tool_msgs[0].content


async def test_agent_without_tools_returns_immediately() -> None:
    prov = MockProvider(script=[LLMResponse(content="hi back", model="mock")])
    agent = Agent(AgentSpec(name="t", role="worker", model="mock"), LLMClient(prov))
    resp = await agent.run("hi")
    assert resp.content == "hi back"
    assert len(prov.calls) == 1

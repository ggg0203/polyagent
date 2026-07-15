"""Tests for DeepSeek DSML tool-call parsing fallback."""

from polyagent.llm.deepseek import _parse_dsml, _strip_dsml
from polyagent.llm.openai_compat import _extract_tool_calls


def test_parse_dsml_web_search() -> None:
    content = """<|DSML| |tool_calls>
<|DSML| |invoke name="web_search">
<|DSML| |parameter name="query" string="true">2026世界杯 7月13日 半决赛</|DSML| |parameter>
</|DSML| |invoke>
</|DSML| |tool_calls>"""
    calls = _parse_dsml(content)
    assert calls is not None
    assert len(calls) == 1
    assert calls[0].name == "web_search"
    import json

    args = json.loads(calls[0].arguments)
    assert args["query"] == "2026世界杯 7月13日 半决赛"


def test_extract_tool_calls_prefers_standard() -> None:
    raw = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "python_execute", "arguments": '{"code": "print(1)"}'},
        }
    ]
    content = "some text with <|DSML| stuff that should be ignored"
    calls, cleaned = _extract_tool_calls(raw, content)
    assert calls is not None
    assert calls[0].name == "python_execute"
    assert cleaned == content


def test_extract_tool_calls_returns_none_when_no_calls() -> None:
    """Generic _extract_tool_calls does NOT parse DSML (DeepSeekProvider.chat handles that)."""
    content = """<|DSML| |tool_calls>
<|DSML| |invoke name="web_search">
<|DSML| |parameter name="query" string="true">hello</|DSML| |parameter>
</|DSML| |invoke>
</|DSML| |tool_calls>"""
    calls, cleaned = _extract_tool_calls(None, content)
    # Generic extractor returns None; DSML is handled by DeepSeekProvider.chat() override
    assert calls is None
    assert cleaned == content


def test_strip_dsml_only() -> None:
    text = 'Before. <|DSML| |tool_calls>...<|DSML| |parameter name="x">v</|DSML| |parameter>...</|DSML| |tool_calls> After.'
    cleaned = _strip_dsml(text)
    assert "<|DSML|" not in cleaned
    assert "Before." in cleaned
    assert "After." in cleaned

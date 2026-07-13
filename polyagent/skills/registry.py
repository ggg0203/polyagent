"""Skill registry — builtin marketplace index of installable skills.

Each skill record describes what the skill does and where to get its code.
The installer uses this metadata to download and load skills.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------- #
# Builtin skill marketplace index
# --------------------------------------------------------------------------- #
# Each entry: {name, version, description, author, source_path, tools}
# source_path: relative to polyagent/skills/builtins/ (bundled) or URL

BUILTIN_SKILLS: list[dict[str, Any]] = [
    {
        "name": "weather",
        "version": "1.0.0",
        "description": "查询任意城市的实时天气（模拟演示，不会真实联网）",
        "author": "PolyAgent",
        "source": "weather_skill.py",
        "tools": ["get_weather"],
    },
    {
        "name": "file_analyzer",
        "version": "1.0.0",
        "description": "分析文件：统计行数/字数/大小，检测编码格式",
        "author": "PolyAgent",
        "source": "file_analyzer_skill.py",
        "tools": ["analyze_file"],
    },
    {
        "name": "datetime_utils",
        "version": "1.0.0",
        "description": "日期时间工具：获取当前时间、计算日期差、格式化时间戳",
        "author": "PolyAgent",
        "source": "datetime_skill.py",
        "tools": ["current_time", "date_diff", "format_timestamp"],
    },
]


def search_skills(query: str) -> list[dict[str, Any]]:
    """Search builtin skills by keyword (case-insensitive, matches name/desc)."""
    q = query.lower()
    return [
        s
        for s in BUILTIN_SKILLS
        if q in s["name"].lower() or q in s["description"].lower()
    ]


def list_skills() -> list[dict[str, Any]]:
    """Return all builtin skills."""
    return list(BUILTIN_SKILLS)

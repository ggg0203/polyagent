"""Tests: skill marketplace registry and installer."""

from __future__ import annotations

from polyagent.skills import BUILTIN_SKILLS, list_installed, list_skills, search_skills


def test_list_skills_returns_all() -> None:
    all_sk = list_skills()
    assert len(all_sk) >= 3
    names = [s["name"] for s in all_sk]
    assert "weather" in names
    assert "file_analyzer" in names
    assert "datetime_utils" in names


def test_search_skills_by_name() -> None:
    hits = search_skills("weather")
    assert len(hits) >= 1
    assert hits[0]["name"] == "weather"


def test_search_skills_by_keyword() -> None:
    hits = search_skills("日期")
    assert len(hits) >= 1


def test_search_skills_no_match() -> None:
    hits = search_skills("zzz_nonexistent_123")
    assert len(hits) == 0


def test_list_installed_empty() -> None:
    """list_installed should always return a list (possibly empty)."""
    result = list_installed()
    assert isinstance(result, list)


def test_builtin_skills_have_required_fields() -> None:
    for s in BUILTIN_SKILLS:
        assert "name" in s
        assert "version" in s
        assert "description" in s
        assert "source" in s
        assert "tools" in s


def test_install_from_url_fails_on_bad_url() -> None:
    """install_from_url with an invalid URL should return an error."""
    from polyagent.skills import install_from_url

    ok, msg = install_from_url("test", "http://127.0.0.1:1/nonexistent.py")
    assert not ok
    assert "download failed" in msg


def test_load_skills_into_empty_dir() -> None:
    """load_skills_into on a clean directory should register 0 tools."""
    from pathlib import Path

    from polyagent.skills.installer import load_skills_into
    from polyagent.tools import ToolRegistry

    reg = ToolRegistry()
    n = load_skills_into(reg)
    assert n == 0


def test_install_and_load_skill() -> None:
    """Install a skill, then load it into a registry and verify tools."""
    import shutil
    from pathlib import Path

    from polyagent.skills import install_builtin
    from polyagent.skills.installer import load_skills_into
    from polyagent.tools import ToolRegistry

    skills_dir = Path.home() / ".polyagent" / "skills"
    if skills_dir.exists():
        shutil.rmtree(skills_dir)

    ok, _ = install_builtin("weather")
    assert ok

    # Verify it appears in list_installed
    installed = list_installed()
    names = [s["name"] for s in installed]
    assert "weather" in names

    # Load into registry
    reg = ToolRegistry()
    n = load_skills_into(reg)
    assert n == 1
    assert "get_weather" in reg.names()

    # Cleanup
    shutil.rmtree(skills_dir)

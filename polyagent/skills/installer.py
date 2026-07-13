"""Skill installer — download, install, and load skills dynamically.

Skills are stored as Python modules in ``~/.polyagent/skills/``.
Each skill module exports ``metadata`` (dict) and ``get_tools()`` (-> list[Tool]).

Install flow:
1. User calls ``marketplace_install`` tool with a skill name
2. Installer copies the builtin skill file to ~/.polyagent/skills/
3. Installer loads the module and registers its tools
4. Tools become available to the Agent on the next turn
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from polyagent.tools.base import Tool
from polyagent.tools.registry import ToolRegistry

# Where installed skills live on disk
SKILLS_DIR = Path.home() / ".polyagent" / "skills"


def _ensure_dir() -> None:
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)


def _builtin_source_path(name: str) -> Path | None:
    """Return the path to a builtin skill source file, or None."""
    from polyagent.skills.registry import BUILTIN_SKILLS

    for skill in BUILTIN_SKILLS:
        if skill["name"] == name:
            src = skill.get("source", "")
            p = Path(__file__).parent / "builtins" / src
            return p if p.is_file() else None
    return None


def install_builtin(name: str) -> tuple[bool, str]:
    """Install a builtin skill by name. Returns (success, message)."""
    src = _builtin_source_path(name)
    if src is None:
        return False, f"unknown skill: {name}"

    _ensure_dir()
    dst = SKILLS_DIR / src.name
    dst.write_bytes(src.read_bytes())
    return True, f"installed {name} v1.0.0 to {dst}"


def install_from_url(name: str, url: str) -> tuple[bool, str]:
    """Download a skill from a URL and install it."""
    import httpx

    _ensure_dir()
    try:
        resp = httpx.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        return False, f"download failed: {exc}"

    dst = SKILLS_DIR / f"{name}.py"
    dst.write_text(resp.text, encoding="utf-8")
    return True, f"installed {name} from {url}"


def uninstall(name: str) -> tuple[bool, str]:
    """Remove an installed skill."""
    py = SKILLS_DIR / f"{name}.py"
    if py.is_file():
        py.unlink()
        return True, f"uninstalled {name}"
    return False, f"not found: {name}"


def list_installed() -> list[dict[str, Any]]:
    """List all locally installed skills."""
    _ensure_dir()
    skills: list[dict[str, Any]] = []
    for py in sorted(SKILLS_DIR.glob("*.py")):
        meta = _load_metadata(py)
        if meta:
            skills.append(meta)
    return skills


def _load_metadata(py: Path) -> dict[str, Any] | None:
    """Load metadata from a skill module without importing its tools."""
    spec = importlib.util.spec_from_file_location(py.stem, py)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return None
    meta = getattr(mod, "metadata", {})
    return {"name": py.stem, **meta}


def load_skills_into(registry: ToolRegistry) -> int:
    """Scan ~/.polyagent/skills/ and register all tools into the given registry.

    Returns the number of tools registered.
    """
    count = 0
    _ensure_dir()
    for py in SKILLS_DIR.glob("*.py"):
        try:
            spec = importlib.util.spec_from_file_location(py.stem, py)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            get_tools = getattr(mod, "get_tools", None)
            if get_tools is None:
                continue
            for tool in get_tools():
                if isinstance(tool, Tool):
                    registry.register(tool)
                    count += 1
        except Exception:
            continue
    return count

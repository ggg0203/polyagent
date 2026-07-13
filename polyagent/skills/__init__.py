"""Skills: marketplace registry, installer, and dynamic tool loading.

Allows PolyAgent to search a skill marketplace, install skills,
and dynamically load their tools into the Agent's tool registry.
"""

from polyagent.skills.installer import (
    install_builtin,
    install_from_url,
    list_installed,
    load_skills_into,
    uninstall,
)
from polyagent.skills.registry import BUILTIN_SKILLS, list_skills, search_skills

__all__ = [
    "BUILTIN_SKILLS",
    "install_builtin",
    "install_from_url",
    "list_installed",
    "list_skills",
    "load_skills_into",
    "search_skills",
    "uninstall",
]

"""Builtin tools: code execution, file I/O, HTTP, and file search (grep).

Sandboxing note: ``PythonExecute`` runs in a *separate process* with a timeout,
which gives process isolation but is NOT a container/SECCOMP sandbox. For
untrusted code, run inside a container. The other tools operate on the host
filesystem/network — register only what your deployment trusts.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from asyncio.subprocess import PIPE
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from polyagent.tools.sandbox import DockerSandbox

import httpx
from pydantic import BaseModel, Field

from polyagent.tools.base import Tool, ToolResult

# --------------------------------------------------------------------------- #
# PythonExecute
# --------------------------------------------------------------------------- #


class PythonExecuteArgs(BaseModel):
    code: str
    timeout: float = 10.0


class PythonExecute(Tool):
    name = "python_execute"
    description = (
        "Execute Python code; returns stdout (or stderr on failure). "
        "Subprocess by default — pass a DockerSandbox for container isolation."
    )
    args_model = PythonExecuteArgs

    def __init__(self, sandbox: DockerSandbox | None = None) -> None:
        self.sandbox = sandbox

    async def run(self, args: PythonExecuteArgs) -> ToolResult:
        if self.sandbox is not None:
            return await self.sandbox.run(args.code, args.timeout)
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            args.code,
            stdout=PIPE,
            stderr=PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=args.timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return ToolResult(output=f"execution timed out after {args.timeout}s", error=True)

        out = stdout.decode(errors="replace")
        err = stderr.decode(errors="replace")
        ok = proc.returncode == 0
        body = out if ok else (err or out)
        return ToolResult(output=body, error=not ok, metadata={"returncode": proc.returncode})


# --------------------------------------------------------------------------- #
# ReadFile / WriteFile
# --------------------------------------------------------------------------- #


class ReadFileArgs(BaseModel):
    path: str
    max_bytes: int = 65536


class ReadFile(Tool):
    name = "read_file"
    description = "Read a file from disk as UTF-8 text (truncated to max_bytes)."
    args_model = ReadFileArgs

    async def run(self, args: ReadFileArgs) -> ToolResult:
        p = Path(args.path)
        if not p.is_file():
            return ToolResult(output=f"not found: {p}", error=True)
        data = p.read_bytes()[: args.max_bytes]
        try:
            text = data.decode()
        except UnicodeDecodeError:
            text = f"<binary {len(data)} bytes, not utf-8>"
        return ToolResult(output=text)


class WriteFileArgs(BaseModel):
    path: str
    content: str
    append: bool = False


class WriteFile(Tool):
    name = "write_file"
    description = "Write text content to a file (overwrite by default, or append)."
    args_model = WriteFileArgs

    async def run(self, args: WriteFileArgs) -> ToolResult:
        p = Path(args.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if args.append else "w"
        with p.open(mode, encoding="utf-8") as f:
            f.write(args.content)
        return ToolResult(output=f"wrote {len(args.content)} chars to {p}")


# --------------------------------------------------------------------------- #
# HttpRequest
# --------------------------------------------------------------------------- #


class HttpRequestArgs(BaseModel):
    method: str = "GET"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    timeout: float = 15.0


class HttpRequest(Tool):
    name = "http_request"
    description = "Perform an HTTP request; return status code + truncated body."
    args_model = HttpRequestArgs

    async def run(self, args: HttpRequestArgs) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=args.timeout) as client:
                resp = await client.request(
                    args.method.upper(),
                    args.url,
                    headers=args.headers,
                    content=args.body,
                )
        except Exception as exc:
            return ToolResult(
                output=f"HTTP request failed: {type(exc).__name__}: {exc}",
                error=True,
            )
        text = resp.text[:8000]
        return ToolResult(
            output=f"HTTP {resp.status_code}\n{text}",
            metadata={"status": resp.status_code},
            error=resp.status_code >= 400,
        )


# --------------------------------------------------------------------------- #
# GrepFiles (local search)
# --------------------------------------------------------------------------- #


class GrepFilesArgs(BaseModel):
    directory: str
    pattern: str
    max_results: int = 50


class GrepFiles(Tool):
    name = "grep_files"
    description = (
        "Recursively search files in a directory for a regex; returns 'path:line:content'."
    )
    args_model = GrepFilesArgs

    async def run(self, args: GrepFilesArgs) -> ToolResult:
        regex = re.compile(args.pattern)
        matches: list[str] = []
        for root, _dirs, files in os.walk(args.directory):
            for fn in files:
                p = Path(root) / fn
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        matches.append(f"{p}:{i}:{line}")
                        if len(matches) >= args.max_results:
                            return ToolResult(output="\n".join(matches))
        return ToolResult(output="\n".join(matches) if matches else "no matches")


# --------------------------------------------------------------------------- #
# WebSearch (multi-engine: Bing / DuckDuckGo / Sogou)
# --------------------------------------------------------------------------- #


class WebSearchArgs(BaseModel):
    query: str = Field(..., description="The search query string.")
    max_results: int = 5
    engine: str = Field(
        "bing",
        description=(
            'Search engine selection. Use "bing" (default, works in China), '
            '"duckduckgo" (requires proxy/VPN), or "sogou" (Chinese).'
        ),
    )


class WebSearch(Tool):
    name = "web_search"
    description = (
        "Search the web for current information. "
        "Returns title + snippet + URL for each result. "
        "Supports engines: bing (default, works in China), duckduckgo, sogou. "
        "Use this for real-time info, news, documentation lookups, etc."
    )
    args_model = WebSearchArgs

    # ── Bing ──────────────────────────────────────────────────────────────── #

    async def _search_bing(self, query: str, max_results: int) -> list[str]:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(
                "https://www.bing.com/search",
                params={"q": query},
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                },
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}")

        results: list[str] = []
        # Each result sits inside <li class="b_algo">.
        blocks = re.findall(r'<li[^>]*class="b_algo"[^>]*>(.*?)</li>', resp.text, re.DOTALL)
        for i, block in enumerate(blocks[:max_results]):
            # Title + link inside <h2 class="..."><a href="URL">TITLE</a></h2>
            m = re.search(r'<h2[^>]*>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', block, re.DOTALL)
            # Snippet inside <p> tag
            s = re.search(r"<p[^>]*>(.*?)</p>", block, re.DOTALL)
            if m:
                href = m.group(1)
                title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                snippet = re.sub(r"<[^>]+>", "", s.group(1)).strip() if s else ""
                results.append(f"{i + 1}. {title}\n   {snippet}\n   {href}")

        return results

    # ── DuckDuckGo (lite) ─────────────────────────────────────────────────── #

    async def _search_duckduckgo(self, query: str, max_results: int) -> list[str]:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.post("https://lite.duckduckgo.com/lite/", data={"q": query})
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}")

        html = resp.text
        links = re.findall(
            r'<a[^>]*rel="nofollow"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        )
        snippets = re.findall(r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>', html, re.DOTALL)

        results: list[str] = []
        for i, (href, title) in enumerate(links[:max_results]):
            title_clean = re.sub(r"<[^>]+>", "", title).strip()
            snippet = ""
            if i < len(snippets):
                snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
            results.append(f"{i + 1}. {title_clean}\n   {snippet}\n   {href}")
        return results

    # ── Sogou ─────────────────────────────────────────────────────────────── #

    async def _search_sogou(self, query: str, max_results: int) -> list[str]:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(
                "https://www.sogou.com/web",
                params={"query": query},
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                },
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}")

        results: list[str] = []
        # Each result sits inside <div class="vrwrap"> or <div class="rb">
        blocks = re.findall(
            r'<div[^>]*class="(?:vrwrap|rb)"[^>]*>(.*?)</div>\s*</div>',
            resp.text,
            re.DOTALL,
        )
        for i, block in enumerate(blocks[:max_results]):
            m = re.search(
                r'<h3[^>]*>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
                block,
                re.DOTALL,
            )
            s = re.search(r'<p[^>]*class="str_info"[^>]*>(.*?)</p>', block, re.DOTALL)
            if m:
                href = m.group(1)
                title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                snippet = re.sub(r"<[^>]+>", "", s.group(1)).strip() if s else ""
                results.append(f"{i + 1}. {title}\n   {snippet}\n   {href}")

        return results

    # ── Dispatcher ────────────────────────────────────────────────────────── #

    async def run(self, args: WebSearchArgs) -> ToolResult:
        engine_map = {
            "bing": self._search_bing,
            "duckduckgo": self._search_duckduckgo,
            "sogou": self._search_sogou,
        }
        searcher = engine_map.get(args.engine)
        if searcher is None:
            return ToolResult(
                output=(f"Unknown engine '{args.engine}'. Supported: {', '.join(engine_map)}"),
                error=True,
            )

        try:
            results = await searcher(args.query, args.max_results)
        except Exception as exc:
            return ToolResult(
                output=f"web search ({args.engine}) failed: {exc}",
                error=True,
            )

        if not results:
            return ToolResult(output=f"No results found for '{args.query}' ({args.engine}).")

        output = f"Web search results for '{args.query}' [{args.engine}]:\n\n" + "\n\n".join(
            results
        )
        return ToolResult(output=output)


# --------------------------------------------------------------------------- #
# MarketplaceSearch / MarketplaceInstall
# --------------------------------------------------------------------------- #


class MarketplaceSearchArgs(BaseModel):
    query: str = Field(..., description="Keyword to search for in the skill marketplace.")


class MarketplaceSearch(Tool):
    name = "marketplace_search"
    description = (
        "Search the PolyAgent skill marketplace for installable skills. "
        "Returns name, version, description, and available tool names for each match."
    )
    args_model = MarketplaceSearchArgs

    async def run(self, args: MarketplaceSearchArgs) -> ToolResult:
        from polyagent.skills import list_skills, search_skills

        results = search_skills(args.query)
        if not results:
            all_sk = list_skills()
            return ToolResult(
                output=f"No skills match '{args.query}'.\n\n"
                f"Available skills ({len(all_sk)}):\n"
                + "\n".join(f"  - {s['name']}: {s['description']}" for s in all_sk)
            )
        lines = [f"Found {len(results)} skill(s) for '{args.query}':\n"]
        for s in results:
            tools = ", ".join(s.get("tools", []))
            lines.append(
                f"  📦 {s['name']} v{s['version']}\n     {s['description']}\n     Tools: {tools}\n"
            )
        return ToolResult(output="\n".join(lines))


class MarketplaceInstallArgs(BaseModel):
    name: str = Field(..., description="Name of the skill to install (see marketplace_search).")


class MarketplaceInstall(Tool):
    name = "marketplace_install"
    description = (
        "Install a skill from the marketplace by name. "
        "After installation, the skill's tools become available for use. "
        "Use marketplace_search first to find skills."
    )
    args_model = MarketplaceInstallArgs

    async def run(self, args: MarketplaceInstallArgs) -> ToolResult:
        from polyagent.skills import install_builtin

        ok, msg = install_builtin(args.name)
        return ToolResult(output=msg, error=not ok)


# --------------------------------------------------------------------------- #
# SkillHub — 腾讯技能市场 (https://skillhub.tencent.com)
# 使用公开 REST API，无需安装 CLI
# --------------------------------------------------------------------------- #

SKILLHUB_SKILLS_DIR = Path.home() / ".polyagent" / "skillhub-skills"
SKILLHUB_SEARCH_URL = "https://api.skillhub.cn/api/v1/search"
SKILLHUB_DOWNLOAD_URL = (
    "https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/skills/{slug}.zip"
)
SKILLHUB_INDEX_URL = "https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/skills.json"


async def _skillhub_search_api(query: str) -> list[dict[str, Any]]:
    """Call SkillHub search API and return results list."""
    import json as _json

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            SKILLHUB_SEARCH_URL,
            params={"q": query},
        )
        if resp.status_code != 200:
            return []
        try:
            data = resp.json()
        except _json.JSONDecodeError:
            return []
    # The API may return different shapes. Try to normalize.
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("results") or data.get("data") or data.get("skills") or []
    return []


async def _skillhub_download_skill(slug: str, dest: Path) -> tuple[bool, str]:
    """Download a SkillHub skill as ZIP and extract to dest directory."""
    import io
    import zipfile

    url = SKILLHUB_DOWNLOAD_URL.format(slug=slug)
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return False, f"download failed: HTTP {resp.status_code}"
    except Exception as exc:
        return False, f"download error: {exc}"

    dest.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            z.extractall(path=str(dest))
    except zipfile.BadZipFile:
        # Some skills are single files, not ZIPs
        dest.joinpath("SKILL.md").write_bytes(resp.content)
    return True, f"downloaded to {dest}"


def _skillhub_parse_search_result(s: dict[str, Any]) -> str:
    """Format one skill search result for display."""
    name = s.get("name") or s.get("slug") or s.get("title", "?")
    slug = s.get("slug") or s.get("id", "")
    desc = s.get("description") or s.get("desc", "")
    tags = s.get("tags") or []
    tag_str = ", ".join(str(t)[:20] for t in tags[:5]) if tags else ""
    author = s.get("author") or s.get("publisher", "")
    parts = [f"  📦 {name} ({slug})"]
    if desc:
        parts.append(f"     {desc[:150]}")
    if tag_str:
        parts.append(f"     标签: {tag_str}")
    if author:
        parts.append(f"     作者: {author}")
    return "\n".join(parts)


class SkillHubSearchArgs(BaseModel):
    query: str = Field(..., description="Keyword to search on SkillHub.")


class SkillHubSearch(Tool):
    name = "skillhub_search"
    description = "Search Tencent SkillHub (skillhub.tencent.com) for 76K+ AI skills by keyword."
    args_model = SkillHubSearchArgs

    async def run(self, args: SkillHubSearchArgs) -> ToolResult:
        results = await _skillhub_search_api(args.query)
        if not results:
            return ToolResult(
                output=f"No results for '{args.query}' on SkillHub. "
                "The API might need a different format; "
                "try a simpler keyword."
            )
        formatted = [_skillhub_parse_search_result(s) for s in results[:15]]
        header = f"SkillHub results for '{args.query}' ({len(results)} found):\n\n"
        footer = ""
        if len(results) > 15:
            footer = f"\n... and {len(results) - 15} more."
        return ToolResult(output=header + "\n\n".join(formatted) + footer)


class SkillHubInstallArgs(BaseModel):
    slug: str = Field(..., description="Slug (identifier) of the skill to install from SkillHub.")


class SkillHubInstall(Tool):
    name = "skillhub_install"
    description = "Install a skill from Tencent SkillHub by slug. Downloads SKILL.md + assets."
    args_model = SkillHubInstallArgs

    async def run(self, args: SkillHubInstallArgs) -> ToolResult:
        dest = SKILLHUB_SKILLS_DIR / args.slug
        ok, msg = await _skillhub_download_skill(args.slug, dest)
        if not ok:
            return ToolResult(output=msg, error=True)

        skill_md = dest / "SKILL.md"
        if skill_md.is_file():
            preview = skill_md.read_text(encoding="utf-8", errors="replace")[:600]
            return ToolResult(
                output=f"OK: installed '{args.slug}'\n  {dest}\n\nSKILL.md preview:\n{preview}"
            )
        # List what was downloaded
        files = [str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file()]
        return ToolResult(
            output=f"OK: installed '{args.slug}'\n  {dest}\n  Files: {', '.join(files[:10])}"
        )


class SkillHubList(Tool):
    name = "skillhub_list"
    description = "List all skills installed from Tencent SkillHub."
    args_model = type("_EmptySHList", (BaseModel,), {})

    async def run(self, args: BaseModel) -> ToolResult:
        if not SKILLHUB_SKILLS_DIR.is_dir():
            return ToolResult(output="No SkillHub skills installed yet.")
        entries = []
        for d in sorted(SKILLHUB_SKILLS_DIR.iterdir()):
            if d.is_dir():
                skill_md = d / "SKILL.md"
                if skill_md.is_file():
                    content = skill_md.read_text(encoding="utf-8", errors="replace")
                    desc = ""
                    for line in content.splitlines():
                        if line.startswith("description:"):
                            desc = line.split(":", 1)[1].strip().strip('"').strip("'")
                            break
                    entries.append(f"  📦 {d.name}: {desc[:100] if desc else '(no desc)'}")
        if not entries:
            return ToolResult(output="No SkillHub skills found.")
        return ToolResult(
            output=f"Installed SkillHub skills ({len(entries)}):\n" + "\n".join(entries)
        )


class SkillHubInstallFromPromptArgs(BaseModel):
    prompt: str = Field(
        ..., description="The official SkillHub installation prompt copied from the website."
    )


class SkillHubInstallFromPrompt(Tool):
    name = "skillhub_install_from_prompt"
    description = (
        "Install a SkillHub skill from the official installation prompt. "
        "Users copy the prompt from the SkillHub website and paste it here. "
        "This tool extracts the skill slug and installs it automatically."
    )
    args_model = SkillHubInstallFromPromptArgs

    async def run(self, args: SkillHubInstallFromPromptArgs) -> ToolResult:

        slug = _extract_skillhub_slug(args.prompt)
        if not slug:
            return ToolResult(
                output="Could not find a skill slug in the prompt. "
                "Expected something like: '安装 pdf-image-text-extractor'\n\n"
                f"Prompt received:\n{args.prompt[:300]}",
                error=True,
            )

        dest = SKILLHUB_SKILLS_DIR / slug
        ok, msg = await _skillhub_download_skill(slug, dest)
        if not ok:
            return ToolResult(output=f"Failed to install '{slug}': {msg}", error=True)

        skill_md = dest / "SKILL.md"
        if skill_md.is_file():
            preview = skill_md.read_text(encoding="utf-8", errors="replace")[:600]
            return ToolResult(
                output=f"OK: installed '{slug}' from SkillHub prompt.\n  {skill_md}\n\nSKILL.md preview:\n{preview}"
            )

        files = [str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file()]
        return ToolResult(
            output=f"OK: installed '{slug}' from prompt.\n  {dest}\n  Files: {', '.join(files[:10])}"
        )


def _extract_skillhub_slug(prompt: str) -> str | None:
    """Extract a skill slug from an official SkillHub installation prompt."""
    import re

    # 1. Try Chinese pattern: 安装 xxx / 安装：xxx
    m = re.search(r"(?:安装|install|安裝)\s*[:：]?\s*([a-zA-Z0-9_-]+)", prompt, re.IGNORECASE)
    if m:
        return m.group(1)

    # 2. Try slug: xxx / slug：xxx
    m = re.search(r"(?:slug|skill)\s*[:：]\s*([a-zA-Z0-9_-]+)", prompt, re.IGNORECASE)
    if m:
        return m.group(1)

    # 3. Try URL path: https://skillhub.cn/install/xxx.md or /skills/{slug}.zip
    m = re.search(
        r"skillhub\.cn/(?:install/|skills/)([a-zA-Z0-9_-]+)(?:\.md|\.zip)?", prompt, re.IGNORECASE
    )
    if m:
        return m.group(1)
    m = re.search(r"skills/([a-zA-Z0-9_-]+)\.zip", prompt, re.IGNORECASE)
    if m:
        return m.group(1)

    return None

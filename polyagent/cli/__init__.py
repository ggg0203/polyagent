"""CLI: version / run / chat / shell / eval / runs / show."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from datetime import datetime

import typer

from polyagent import __version__
from polyagent.cli.demo import build_demo_orchestrator


def _resolve_provider(provider: str | None) -> str:
    """Auto-detect: deepseek if key is set, otherwise mock."""
    if provider:
        return provider
    return "deepseek" if os.getenv("DEEPSEEK_API_KEY") else "mock"


app = typer.Typer(
    name="polyagent",
    help="PolyAgent — a model-agnostic multi-agent orchestration framework.",
    no_args_is_help=True,
)


@app.callback()
def _main() -> None:
    """PolyAgent CLI."""


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(__version__)


@app.command()
def run(
    goal: str = typer.Argument(help="The goal to decompose and execute."),
    provider: str | None = typer.Option(
        None, help="mock | deepseek (default: auto-detect from DEEPSEEK_API_KEY)."
    ),
    persist: bool = typer.Option(True, help="Save the run to polyagent.db."),
) -> None:
    """Run the multi-agent pipeline on a goal."""
    provider = _resolve_provider(provider)
    asyncio.run(_run_async(goal, provider, persist))


async def _run_async(goal: str, provider: str, persist: bool = True) -> None:
    if provider == "mock":
        orch, tracer, cost = build_demo_orchestrator()
    elif provider == "deepseek":
        from polyagent.cli.demo import build_deepseek_orchestrator

        try:
            orch, tracer, cost = build_deepseek_orchestrator()
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from exc
    else:
        typer.echo(f"unknown provider '{provider}'; use mock or deepseek.", err=True)
        raise typer.Exit(1)
    result = await orch.run(goal)
    typer.echo(f"Answer: {result.answer}")
    typer.echo("Task graph:")
    for task in result.task_graph:
        typer.echo(
            f"  [{task.status.value}] {task.id}: {task.description} (attempts={task.attempts})"
        )
    typer.echo(
        f"Cost: ${cost.estimated_cost_usd:.6f} | Latency: {result.latency:.3f}s | "
        f"Attempts: {result.total_attempts} | Trace roots: {len(tracer.roots)}"
    )
    if persist:
        from polyagent.persistence import RunStore

        store = RunStore()
        run_id = store.save(goal=goal, result=result, trace=tracer.to_dict())
        store.close()
        typer.echo(f"Run ID: {run_id} (saved to polyagent.db)")

    # Observability export (only if backends configured in .env)
    from polyagent.config import get_observability_settings

    obs = get_observability_settings()
    if obs.otel_exporter_otlp_endpoint:
        try:
            from polyagent.observability import export_traces_to_otlp

            n = export_traces_to_otlp(tracer, obs.otel_exporter_otlp_endpoint)
            typer.echo(f"Exported {n} spans to OTLP")
        except ImportError:
            typer.echo("OTLP export needs: pip install '.[observability]'", err=True)
    if obs.prometheus_pushgateway:
        try:
            from polyagent.observability import Metrics, export_metrics_to_prometheus

            m = Metrics()
            m.inc("runs")
            m.observe("run_latency_s", result.latency)
            m.inc("run_cost_usd", result.estimated_cost_usd)
            export_metrics_to_prometheus(m, obs.prometheus_pushgateway)
            typer.echo("Pushed metrics to Prometheus pushgateway")
        except ImportError:
            typer.echo("Prometheus export needs: pip install '.[observability]'", err=True)


@app.command()
def chat(
    provider: str | None = typer.Option(
        None, help="mock | deepseek (default: auto-detect from DEEPSEEK_API_KEY)."
    ),
    stream: bool = typer.Option(False, help="Stream tokens live (deepseek only)."),
) -> None:
    """Interactive single-agent chat (Ctrl-D to exit)."""
    provider = _resolve_provider(provider)
    asyncio.run(_chat_async(provider, stream))


async def _chat_async(provider: str, stream: bool) -> None:
    from polyagent.core.agent import Agent
    from polyagent.core.types import AgentSpec
    from polyagent.llm.client import LLMClient
    from polyagent.llm.deepseek import DeepSeekProvider
    from polyagent.llm.mock import MockProvider

    if provider == "mock":
        spec = AgentSpec(name="chat", role="worker", model="mock")
        agent = Agent(spec, LLMClient(MockProvider()))
    elif provider == "deepseek":
        from polyagent.config import get_settings

        s = get_settings()
        if not s.api_key:
            typer.echo("DEEPSEEK_API_KEY not set; check .env.", err=True)
            raise typer.Exit(1)
        spec = AgentSpec(
            name="chat",
            role="worker",
            model=s.model,
            system_prompt="You are a helpful assistant.",
        )
        ds = DeepSeekProvider(api_key=s.api_key, base_url=s.base_url, model=s.model)
        agent = Agent(spec, LLMClient(ds))
    else:
        typer.echo(f"unknown provider '{provider}'.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Chat ({provider}). Ctrl-D to exit.")
    while True:
        try:
            line = input("you> ")
        except EOFError:
            break
        if not line.strip():
            continue
        if stream and provider == "deepseek":
            typer.echo("agent> ", nl=False)
            async for chunk in agent.run_stream(line):
                typer.echo(chunk, nl=False)
            typer.echo()
        else:
            resp = await agent.run(line)
            typer.echo(f"agent> {resp.content}")


# --------------------------------------------------------------------------- #
# shell — 带全套工具的智能助手
# --------------------------------------------------------------------------- #


_SHELL_PROMPT = """\
You are a powerful AI terminal assistant running inside a Python framework. \
You have the following tools at your disposal. USE THEM PROACTIVELY — do not \
just talk, DO things.

## Available tools

- **web_search(query, max_results=5, engine="bing")** — Search the web for current \
information. Supports engines: bing (default, works in China), duckduckgo, sogou. \
Use this for real-time data, news, documentation, facts you're unsure about.
- **python_execute(code, timeout=10)** — Execute Python code and return stdout/stderr. \
Use this for calculations, system info, data processing, generating content.
- **read_file(path, max_bytes=65536)** — Read a text file from the local filesystem.
- **write_file(path, content, append=False)** — Write text content to a local file.
- **http_request(method, url, headers={}, body=None, timeout=15)** — Make HTTP requests \
to any URL. Use this for fetching API data, downloading content, checking websites.
- **grep_files(directory, pattern, max_results=50)** — Search files for a regex pattern.
- **marketplace_search(query)** — Search the PolyAgent builtin marketplace.
- **marketplace_install(name)** — Install a builtin skill. Tools available next turn.
- **skillhub_search(query)** — Search **Tencent SkillHub** (skillhub.tencent.com) with 76,000+ AI skills.
- **skillhub_install(slug)** — Install a skill from Tencent SkillHub by slug. Downloads SKILL.md + assets.
- **skillhub_install_from_prompt(prompt)** — Install a SkillHub skill from the official
  prompt the user copied from the website. Extracts the skill slug and installs automatically.
- **skillhub_list()** — List installed SkillHub skills with descriptions.

## Skill marketplaces

You have two skill marketplaces:

1. **PolyAgent builtin** (marketplace_search / marketplace_install):
   - weather: query weather for any city
   - file_analyzer: analyze file stats (lines, size, encoding)
   - datetime_utils: current time, date diff, timestamp formatting

2. **Tencent SkillHub** (skillhub_search / skillhub_install / skillhub_install_from_prompt / skillhub_list):
   - 76,000+ AI skills from https://skillhub.tencent.com
   - Skills cover: coding helpers, PDF processing, data analysis, web scraping, etc.
   - Uses direct REST API (no CLI needed). Search by keyword, install by slug.
   - **Official install prompt**: when the user copies the prompt from a SkillHub skill page
     and pastes it, call skillhub_install_from_prompt(prompt_text) immediately.
   - After installing, read the SKILL.md with read_file to understand its instructions.

When the user asks for something not covered by your current tools, first search the \
PolyAgent marketplace, then try SkillHub. Search SkillHub with simple keywords.

**⚠️ CRITICAL RULE: When the user asks to search for skills on SkillHub, Tencent SkillHub, \
腾讯技能市场, or any skill marketplace — you MUST call skillhub_search(query) directly. \
Do NOT use web_search to search for SkillHub or its website. The skillhub_search tool calls \
the official SkillHub API directly. Similarly, use skillhub_install(slug) to install, not web_search or http_request.**

## Behaviour rules

1. When the user asks about current events, web data, or anything recent → call web_search.
2. When asked to calculate, transform data, or generate something → call python_execute.
3. When asked to read/show a file → call read_file.
4. When asked to save/write something → call write_file.
5. When asked to download content or call an API → call http_request.
6. **When asked to search/install skills from SkillHub → call skillhub_search / skillhub_install**.
7. You can chain multiple tool calls. After each tool result, decide whether you need \
more tools or can give the final answer.
8. **Always explain briefly what you're doing** before or during tool calls.
9. When you have all the information needed, give a clear, complete answer.
10. Be concise but thorough. Write Chinese when the user writes Chinese.

## ⚠️ Search strategy (CRITICAL)

- **Stop searching after 3 web_search attempts** if you keep getting no results. \
Do not keep trying different queries endlessly.
- After max 3 searches, immediately summarize what you found (even if nothing) \
and give a direct answer. Do not ask the user for more information.
- If Bing returns nothing, try switching engine="sogou" once. If that also fails, \
stop and answer with what you have.
- **Always give a complete final answer** after searching. Never leave the user \
waiting or ask the user to provide missing info.\
"""


@app.command()
def shell(
    stream: bool = typer.Option(True, help="Show streaming output."),
) -> None:
    """Interactive AI assistant with all tools (web search, code exec, file I/O, ...)."""
    asyncio.run(_shell_async(stream))


async def _shell_async(stream: bool) -> None:
    from polyagent.config import get_settings
    from polyagent.core.agent import Agent
    from polyagent.core.types import AgentSpec, Message, Role
    from polyagent.llm.client import LLMClient
    from polyagent.llm.deepseek import DeepSeekProvider
    from polyagent.llm.types import LLMRequest
    from polyagent.persistence.chat_store import ChatStore
    from polyagent.skills import list_installed, load_skills_into
    from polyagent.tools import with_builtins

    s = get_settings()
    if not s.api_key:
        typer.echo("DEEPSEEK_API_KEY not set; check .env.", err=True)
        raise typer.Exit(1)

    ds = DeepSeekProvider(api_key=s.api_key, base_url=s.base_url, model=s.model)
    tools = with_builtins()

    # Load previously installed skills
    n_registered = load_skills_into(tools)
    installed_skills = list_installed()

    spec = AgentSpec(
        name="shell",
        role="worker",
        model=s.model,
        system_prompt=_SHELL_PROMPT,
    )
    agent = Agent(spec, LLMClient(ds), tools=tools, max_tool_iters=8)

    typer.echo("PolyAgent Shell — 联网搜索 / 代码执行 / 读写文件 / 技能市场")
    typer.echo(f"  Provider: {s.model}  |  内置工具: {', '.join(tools.names())}")
    if installed_skills:
        names = [s["name"] for s in installed_skills]
        typer.echo(f"  📦 已安装技能: {', '.join(names)} ({n_registered} 个工具)")
    typer.echo("  Ctrl-D 退出 | 输入需求，Agent 自动决定用什么工具")
    typer.echo("    提示: 可先用「搜索技能仓库」来查找可安装的技能\n")

    messages: list[Message] = []
    if spec.system_prompt:
        messages.append(Message(role=Role.SYSTEM, content=spec.system_prompt))

    # Load and inject last session's context as a SYSTEM reminder
    chat_store = ChatStore()
    history = chat_store.load_last_session("shell")
    if history:
        summary = "以下是你上次的对话记录，供参考上下文：\n\n"
        for m in history:
            label = {"user": "你说", "assistant": "我说"}.get(m.role.value, m.role.value)
            text = m.content[:300] if m.content else ""
            if m.tool_calls:
                names = [tc.name for tc in m.tool_calls]
                text = f"[调用了: {', '.join(names)}]"
            summary += f"{label}：{text}\n"
        messages.append(Message(role=Role.SYSTEM, content=summary))
        typer.echo(f"  💬 已加载上次对话记录 ({len(history)} 条)\n")

    while True:
        try:
            line = input("you> ")
        except EOFError:
            break
        if not line.strip():
            continue

        messages.append(Message(role=Role.USER, content=line))
        tool_schemas = tools.schemas()

        full_answer = ""
        for iteration in range(agent.max_tool_iters):
            # --- LLM call ---
            req = LLMRequest(
                model=spec.model,
                messages=messages,
                temperature=spec.temperature,
                tools=tool_schemas,
            )
            try:
                resp = await agent.client.chat(req)
            except Exception as exc:
                typer.echo(f"\n  ⚠️ LLM 调用异常: {exc}")
                typer.echo("  对话已恢复，请重新输入。\n")
                break

            # --- stream output ---
            if resp.content:
                if iteration == 0:
                    typer.echo("agent> ", nl=False)
                typer.echo(resp.content, nl=False)
                full_answer += resp.content

            # --- check tool calls ---
            if not resp.tool_calls:
                typer.echo()
                break  # done

            # Append assistant message ONCE before executing tools
            messages.append(
                Message(
                    role=Role.ASSISTANT,
                    content=resp.content,
                    tool_calls=resp.tool_calls,
                )
            )

            # execute each tool and show result
            for call in resp.tool_calls:
                try:
                    args = json.loads(call.arguments) if call.arguments else {}
                except json.JSONDecodeError:
                    args = {}

                args_str = ", ".join(f"{k}={repr(v)[:60]}" for k, v in args.items())
                typer.echo(f"\n  ⚡ 调用 {call.name}({args_str})")

                tool = tools.get(call.name)
                result = await tool.call(args)

                status = "✅" if not result.error else "❌"
                output_preview = result.output[:300].replace("\n", "  ")
                typer.echo(f"  {status} {output_preview}")
                if len(result.output) > 300:
                    typer.echo(f"  ... ({len(result.output)} 字符，已截断)")

                # append tool result to conversation (cap at 2000 chars)
                content = result.output[:2000]
                if len(result.output) > 2000:
                    content += "\n...(truncated)"
                messages.append(Message(role=Role.TOOL, content=content, tool_call_id=call.id))
        else:
            # Tool iterations exhausted — force a final summary without tools
            typer.echo()
            try:
                final_req = LLMRequest(
                    model=spec.model,
                    messages=messages,
                    temperature=spec.temperature,
                    tools=None,
                )
                final_resp = await agent.client.chat(final_req)
                if final_resp.content:
                    typer.echo("agent> ", nl=False)
                    typer.echo(final_resp.content)
                    full_answer = final_resp.content
            except Exception as exc:
                typer.echo(f"  ⚠️ 总结失败: {exc}")

        # reset messages for next user input
        if full_answer:
            messages.append(Message(role=Role.ASSISTANT, content=full_answer))

        # Persist conversation to SQLite for cross-session memory
        with contextlib.suppress(Exception):
            chat_store.save_messages(messages, "shell")


# --------------------------------------------------------------------------- #
# talk — 聊天模式（拟人化，隐藏工具调用）
# --------------------------------------------------------------------------- #

_TALK_PROMPT = """\
You are a warm, intelligent friend. You talk like a real person — friendly, casual, with a \
sense of humor. But you are also smart: you use web search and other tools behind the scenes \
whenever you need up-to-date information.

## The #1 rule (NON-NEGOTIABLE)
When the user asks about **current events, sports matches, weather, schedules, recent news, \
or anything time-sensitive**, you MUST call web_search FIRST, before you say anything. \
Do not answer from your training data. Do not guess. Get the latest info, then answer naturally.

## How to use tools (silently)
- You have web_search, python_execute, read_file, write_file, http_request. Use them silently.
- NEVER tell the user you're searching or using tools.
- NEVER say "based on my search" or "according to". Just answer as if you already know.
- If the first search query doesn't find good results, try another query (max 3 attempts). \
Then stop and answer with what you found.

## Example
User: 明天世界杯谁会赢？
Your action: call web_search(query='2026世界杯 7月13日 半决赛 对阵')
Your response: 哈哈，我看了下，明天半决赛是 A 队对 B 队。A 队最近状态……我反而更看好 B 队，你支持哪边？

## Response style
- Be warm, concise, and natural. Use Chinese when the user writes Chinese.
- Weave facts into conversation, don't list them robotically.
- Express opinions and emotions when appropriate.
- After answering, occasionally ask a short, natural follow-up about the user's opinion or experience.

## What NOT to do
- NEVER answer from your training data cutoff. ALWAYS use web_search for anything current.
- NEVER guess dates like "现在是 1 月" or "比赛还没开始". If search results are insufficient, \
say "我搜了一圈，没找到这场比赛/信息" naturally.
- NEVER ask clarifying questions to answer the question. If the query is vague, answer based on \
your best interpretation.
- NEVER say "你是不是想问欧洲杯/美洲杯/亚洲杯". If search shows no relevant match, just say \
"明天好像没有世界杯比赛" and mention what is happening.
- NEVER ask the user to provide missing information so you can answer. If you can't find it, \
just admit it casually.\
"""


@app.command()
def talk(
    temperature: float = typer.Option(1.0, help="Creativity (0-2, default 1.0)."),
) -> None:
    """Chat mode — emotional, human-like, no tech output."""
    asyncio.run(_talk_async(temperature))


async def _talk_async(temperature: float) -> None:
    from polyagent.config import get_settings
    from polyagent.core.agent import Agent
    from polyagent.core.types import AgentSpec, Message, Role
    from polyagent.llm.client import LLMClient
    from polyagent.llm.deepseek import DeepSeekProvider
    from polyagent.llm.types import LLMRequest
    from polyagent.persistence.chat_store import ChatStore
    from polyagent.tools import with_builtins

    s = get_settings()
    if not s.api_key:
        typer.echo("DEEPSEEK_API_KEY not set; check .env.", err=True)
        raise typer.Exit(1)

    ds = DeepSeekProvider(api_key=s.api_key, base_url=s.base_url, model=s.model)
    tools = with_builtins()

    prompt = f"Today is {datetime.now().strftime('%Y-%m-%d')}.\n\n{_TALK_PROMPT}"

    spec = AgentSpec(
        name="talk",
        role="worker",
        model=s.model,
        temperature=temperature,
        system_prompt=prompt,
    )
    agent = Agent(spec, LLMClient(ds), tools=tools, max_tool_iters=6)

    typer.echo("💬 聊天模式 (talk) — 拟人化对话 / 联网 / 代码执行")
    typer.echo(f"  Provider: {s.model}  |  输入 exit 或 Ctrl-D 退出\n")

    messages: list[Message] = []
    if spec.system_prompt:
        messages.append(Message(role=Role.SYSTEM, content=spec.system_prompt))

    # Load and inject last session's context as a SYSTEM reminder
    chat_store = ChatStore()
    history = chat_store.load_last_session("talk")
    if history:
        summary = "以下是你上次的对话记录，供参考上下文：\n\n"
        for m in history:
            label = {"user": "你说", "assistant": "我说"}.get(m.role.value, m.role.value)
            text = m.content[:300] if m.content else ""
            if m.tool_calls:
                names = [tc.name for tc in m.tool_calls]
                text = f"[调用了: {', '.join(names)}]"
            summary += f"{label}：{text}\n"
        messages.append(Message(role=Role.SYSTEM, content=summary))
        typer.echo(f"  💬 已加载上次对话记录 ({len(history)} 条)\n")

    while True:
        try:
            line = input("你> ")
        except EOFError:
            break
        if not line.strip():
            continue
        if line.strip().lower() == "exit":
            break

        messages.append(Message(role=Role.USER, content=line))
        tool_schemas = tools.schemas()

        full_answer = ""
        for _iteration in range(agent.max_tool_iters):
            req = LLMRequest(
                model=spec.model,
                messages=messages,
                temperature=spec.temperature,
                tools=tool_schemas,
            )
            try:
                resp = await agent.client.chat(req)
            except Exception:
                # silently retry or break — user never sees the error
                break

            full_answer += resp.content or ""

            if not resp.tool_calls:
                break

            # Append assistant message + execute tools SILENTLY
            messages.append(
                Message(
                    role=Role.ASSISTANT,
                    content=resp.content,
                    tool_calls=resp.tool_calls,
                )
            )
            for call in resp.tool_calls:
                tool = tools.get(call.name)
                if tool:
                    try:
                        args = json.loads(call.arguments) if call.arguments else {}
                        result = await tool.call(args)
                        content = (result.output or "")[:2000]
                    except Exception:
                        content = ""
                    messages.append(
                        Message(
                            role=Role.TOOL,
                            content=content,
                            tool_call_id=call.id,
                        )
                    )
        else:
            # Force final summary without tools
            try:
                final_req = LLMRequest(
                    model=spec.model,
                    messages=messages,
                    temperature=spec.temperature,
                    tools=None,
                )
                final_resp = await agent.client.chat(final_req)
                if final_resp.content:
                    full_answer = final_resp.content
            except Exception:
                pass

        # Output only the final answer — no tech noise
        if full_answer:
            typer.echo(f"\n🤖 {full_answer}\n")
            messages.append(Message(role=Role.ASSISTANT, content=full_answer))

        # Persist conversation to SQLite for cross-session memory
        with contextlib.suppress(Exception):
            chat_store.save_messages(messages, "talk")


@app.command("eval")
def eval_() -> None:
    """Run the default eval dataset and print a pass-rate report."""
    asyncio.run(_eval_async())


async def _eval_async() -> None:
    from polyagent.core.agent import Agent
    from polyagent.core.types import AgentSpec
    from polyagent.eval import ContainsScorer, Dataset, EvalRunner
    from polyagent.llm.client import LLMClient
    from polyagent.llm.mock import MockProvider

    agent = Agent(AgentSpec(name="eval", role="worker", model="mock"), LLMClient(MockProvider()))

    async def subject(inp: str) -> str:
        return (await agent.run(inp)).content

    report = await EvalRunner(subject, ContainsScorer()).run(Dataset.default())
    typer.echo(
        f"Eval: {report.passed}/{report.n} passed ({report.pass_rate:.0%}), "
        f"avg_score={report.avg_score:.2f}"
    )
    for r in report.results:
        flag = "PASS" if r.passed else "FAIL"
        typer.echo(f"  [{flag}] {r.case_id}")


@app.command("runs")
def runs_(limit: int = typer.Option(20, help="Max runs to list.")) -> None:
    """List recent persisted runs."""
    from polyagent.persistence import RunStore

    store = RunStore()
    rows = store.list(limit)
    store.close()
    if not rows:
        typer.echo("no runs yet.")
        return
    for r in rows:
        typer.echo(
            f"{r['id']}  ${r['cost_usd']:.6f}  {r['latency']:.2f}s  "
            f"{r['created_at']}  {r['goal'][:40]}"
        )


@app.command("show")
def show(run_id: str = typer.Argument(help="Run id to inspect.")) -> None:
    """Show a run's answer, task graph, and trace summary."""
    from polyagent.persistence import RunStore

    store = RunStore()
    data = store.get(run_id)
    store.close()
    if not data:
        typer.echo(f"run not found: {run_id}", err=True)
        raise typer.Exit(1)
    run = data["run"]
    typer.echo(f"Run {run['id']}: {run['goal']}")
    typer.echo(f"Answer: {run['answer']}")
    typer.echo(f"Cost: ${run['cost_usd']:.6f} | Latency: {run['latency']}s")
    typer.echo("Tasks:")
    for t in data["tasks"]:
        typer.echo(f"  [{t['status']}] {t['id']}: {t['description']} (attempts={t['attempts']})")
    trace = data["trace"]
    if trace:
        roots = trace.get("spans", [])
        typer.echo(f"Trace: {len(roots)} root span(s)")


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()

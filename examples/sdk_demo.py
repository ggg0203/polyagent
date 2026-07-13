"""PolyAgent SDK 演示脚本 — 展示三种 SDK 用法。

运行方式（在项目目录下）：
    python examples/sdk_demo.py

全部用 MockProvider（离线），不依赖 API Key，开箱即跑。
"""

import asyncio

# ─── 用法 1: 单 Agent ────────────────────────────────────
from polyagent.core import Agent, AgentSpec
from polyagent.llm import LLMClient, MockProvider
from polyagent.llm.mock import LLMResponse  # Mock 模式下预设返回内容用


async def demo_single_agent():
    """最简单的用法：创建一个 Agent，让它回答问题。"""
    print("=" * 56)
    print("1️⃣  单 Agent — 基础对话")
    print("=" * 56)

    # 1. 定义 Agent 的角色
    spec = AgentSpec(
        name="assistant",
        role="assistant",
        model="mock",
        system_prompt="你是一个乐于助人的助手。",
    )

    # 2. 创建 LLM 客户端（这里用 Mock，真实场景换 DeepSeekProvider）
    client = LLMClient(MockProvider())

    # 3. 组装 Agent
    agent = Agent(spec, client)

    # 4. 运行 Agent
    resp = await agent.run("你好，你是谁？")
    print(f"  user> 你好，你是谁？")
    print(f"  agent> {resp.content}")
    print()


# ─── 用法 2: Agent + 工具调用 ──────────────────────────────
from polyagent.tools import with_builtins


async def demo_agent_with_tools():
    """Agent 带着工具：Agent 可以执行代码、读文件、发 HTTP 请求。"""
    print("=" * 56)
    print("2️⃣  单 Agent + 工具调用")
    print("=" * 56)

    spec = AgentSpec(
        name="coder",
        role="worker",
        model="mock",
        system_prompt="你是一个会写代码的助手。用 python_execute 工具来执行代码。",
    )

    # 带内置工具（PythonExecute, ReadFile, WriteFile, HttpRequest, GrepFiles）
    agent = Agent(
        spec,
        LLMClient(MockProvider()),
        tools=with_builtins(),
    )

    # 预设工具调用链：Agent 先执行一段 Python 代码，再返回结果
    # 注意：MockProvider 在模拟模式下不真正调用 LLM，这里展示的是真实 LLM 会走的过程
    resp = await agent.run("计算 1 到 100 的和")
    print(f"  user> 计算 1 到 100 的和")
    print(f"  agent> {resp.content}")
    print(f"  (使用 {len(resp.tool_calls or [])} 次工具调用)")
    print()


# ─── 用法 3: 多 Agent 编排（Planner → Workers → Critic → Synthesizer）─
from polyagent.orchestration import Orchestrator, Planner, Worker, Critic, Synthesizer
from polyagent.observability import Tracer
from polyagent.core.types import CostReport


def _make_agent(
    name: str,
    role: str,
    system_prompt: str,
    script: list[LLMResponse] | None = None,
    default: LLMResponse | None = None,
) -> Agent:
    """辅助函数：快速创建一个 Mock 模式的 Agent。

    script: MockProvider 预设的返回序列——模拟 LLM 不同轮次输出不同内容。
    default: 超出 script 序列后用此值兜底；默认用 role 名占位。
    """
    if default is None:
        default = LLMResponse(content=f"[{role} mock output]", model="mock")
    return Agent(
        AgentSpec(name=name, role=role, model="mock", system_prompt=system_prompt),
        LLMClient(MockProvider(script=script or [], default=default)),
    )


async def demo_orchestrator():
    """多 Agent 流水线 — 框架的杀手级特性。

    Pipeline:
        Planner(分解任务) → Workers(并发执行) → Critic(评审) → Synthesizer(汇总)
    """
    print("=" * 56)
    print("3️⃣  多 Agent 编排流水线")
    print("=" * 56)
    print("      Planner → Workers(并行) → Critic → Synthesizer")
    print()

    # ==================== 1. 定义各个 Role ====================

    # Planner: 把用户目标拆成子任务（输出 JSON 任务列表）
    PLAN_JSON = (
        '[{"id":"t1","description":"搜集项目基本信息","deps":[]},'
        '{"id":"t2","description":"检查代码风格","deps":["t1"]},'
        '{"id":"t3","description":"生成总结报告","deps":["t2"]}]'
    )
    planner = Planner(
        _make_agent(
            "planner", "planner",
            "你将用户需求分解为 DAG 任务列表，输出 JSON。",
            script=[LLMResponse(content=PLAN_JSON, model="mock")],
        )
    )

    # Worker: 并发执行子任务（可带工具）
    worker = Worker(
        _make_agent(
            "worker", "worker",
            "你执行分配给你的子任务并报告结果。",
        )
    )

    # Critic: 评审每个任务的输出，决定是否通过或重做
    ACCEPT = LLMResponse(content='{"accepted":true,"feedback":"ok"}', model="mock")
    critic = Critic(
        _make_agent(
            "critic", "critic",
            "你评审任务输出质量，给出 accepted 或 feedback。",
            script=[ACCEPT, ACCEPT, ACCEPT],  # 3个任务各需要一次评审
            default=ACCEPT,                     # 超出预设也用 ACCEPT 兜底
        )
    )

    # Synthesizer: 把所有结果汇总成最终答案
    FINAL = LLMResponse(content="[最终报告] 项目分析完成：结构良好，3个模块，无明显问题。", model="mock")
    synthesizer = Synthesizer(
        _make_agent(
            "synthesizer", "synthesizer",
            "你将所有子任务结果汇总为一份清晰报告。",
            script=[FINAL],
        )
    )

    # ==================== 2. 组装编排器 ====================
    tracer = Tracer()
    cost = CostReport()
    orchestrator = Orchestrator(
        planner, worker, critic, synthesizer,
        tracer=tracer,
        cost_report=cost,
        max_review_retries=2,  # 最多重评审 2 次
    )

    # ==================== 3. 运行 ====================
    print("  🚀 启动编排流水线...")
    print()
    result = await orchestrator.run("分析当前项目的代码质量")

    # ==================== 4. 查看结果 ====================
    print(f"  ✅ 最终答案:")
    print(f"     {result.answer}")
    print()
    print(f"  📊 运行统计:")
    print(f"     - 总任务数:       {len(result.task_graph)}")
    print(f"     - 总尝试次数:     {result.total_attempts}")
    print(f"     - 总耗时:         {result.latency:.3f}s")
    print(f"     - 预估成本:       ${result.estimated_cost_usd:.6f}")
    print(f"     - Trace 根节点数: {len(tracer.roots)}")
    print()
    print(f"  🔍 任务依赖图 (DAG):")
    for task in result.task_graph:
        deps = ", ".join(task.deps) if task.deps else "(无)"
        print(f"     [{task.id}] {task.description}  ← 依赖: {deps}")

    # ==================== 5. 查看 Trace（可观测性） ====================
    print()
    roots = tracer.roots
    print(f"  📝 Trace 详情 (Span 树):")
    if roots:
        for root in roots:
            dur = ((root.end or 0) - root.start) * 1000
            print(f"     └─ {root.name} ({dur:.1f}ms)")
            for child in root.children:
                cdur = ((child.end or 0) - child.start) * 1000
                print(f"        └─ {child.name} ({cdur:.1f}ms)")
    else:
        print(f"     (无 Trace——Mock 模式下未记录)")


# ─── 主入口 ───────────────────────────────────────────
async def main():
    await demo_single_agent()
    await demo_agent_with_tools()
    await demo_orchestrator()


if __name__ == "__main__":
    asyncio.run(main())

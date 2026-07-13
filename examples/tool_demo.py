"""PolyAgent 工具调用演示：Agent 真正执行代码来回答问题。

运行方式：
    python examples/tool_demo.py

本 demo 用 MockProvider 预设了一次 tool_call，展示 Agent 的工具循环：
    LLM 决定调用 python_execute → 工具运行 Python 代码 → 结果返回 LLM → 给出最终答案。

把 provider 换成 DeepSeekProvider 后，LLM 会自己决定何时调用工具，真实执行代码。
"""

import asyncio
import json

from polyagent.core import Agent, AgentSpec
from polyagent.core.types import ToolCall
from polyagent.llm import LLMClient, MockProvider
from polyagent.llm.types import LLMResponse as LLMResponseType
from polyagent.tools import with_builtins


async def main():
    print("=" * 60)
    print("Agent + 工具调用：计算 1+2+...+100")
    print("=" * 60)

    # 1. Agent 角色：明确告诉它可以调用 python_execute
    spec = AgentSpec(
        name="coder",
        role="worker",
        model="mock",
        system_prompt=(
            "你是一个会写 Python 代码的助手。"
            "当用户要求计算时，调用 python_execute 工具执行代码，然后总结结果。"
        ),
    )

    # 2. Mock 预设：模拟 LLM 第一次返回一个 tool_call，要求执行 Python 代码
    tool_response = LLMResponseType(
        model="mock",
        content="我来计算一下 1 到 100 的和。",
        tool_calls=[
            ToolCall(
                id="call_1",
                name="python_execute",
                arguments=json.dumps({"code": "print(sum(range(1, 101)))", "timeout": 10.0}),
            )
        ],
    )

    # 3. Mock 预设：第二次返回最终结果（在拿到工具结果后）
    final_response = LLMResponseType(
        model="mock",
        content="1 到 100 的和是 5050。",
    )

    # 4. 创建带工具的 Agent
    agent = Agent(
        spec,
        LLMClient(MockProvider(script=[tool_response, final_response])),
        tools=with_builtins(),
        max_tool_iters=2,
    )

    # 5. 运行：注意工具调用在 Agent 内部完成，返回的是最终答案
    print("\n  user> 计算 1+2+...+100\n")
    print("  [Agent 工具循环] 调用 python_execute 执行: print(sum(range(1, 101)))")
    resp = await agent.run("计算 1+2+...+100")
    print("  [工具输出] 5050")
    print(f"  agent> {resp.content}\n")


if __name__ == "__main__":
    asyncio.run(main())

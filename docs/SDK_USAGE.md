# PolyAgent (scgnb666) — SDK 使用说明书

> 包名：`scgnb666`（pip 安装用）
> Python 导入名：`polyagent`（代码中 import 用）
> 版本：0.1.0
> 作者：PolyAgent Contributors
> 许可证：MIT

---

## 一、快速安装

```bash
pip install scgnb666
```

如需可选功能：

```bash
# 完整安装（包含 RAG、可观测性、开发工具）
pip install scgnb666[rag,observability,dev]
```

---

## 二、配置 DeepSeek API（可选）

**安装后直接就能用，默认 Mock 模式（离线，无需任何配置）。**

如果想用真实 DeepSeek，有两种方式：

### 方式 A：设置环境变量（推荐）

```bash
# Windows PowerShell
$env:DEEPSEEK_API_KEY="sk-你的key"
python 你的脚本.py
```

设置后，SDK 会自动检测并使用 DeepSeek。不设置则自动走 Mock。

### 方式 B：代码中直接传参

```python
from polyagent.llm.deepseek import DeepSeekProvider
from polyagent.llm.client import LLMClient

client = LLMClient(DeepSeekProvider(api_key="sk-你的key"))
```

### CLI 默认行为

`polyagent chat` 和 `polyagent run` 命令也遵循自动检测规则：
- 有 `DEEPSEEK_API_KEY` → 自动用 DeepSeek
- 没有 → 自动用 Mock

也可以显式指定：

```bash
polyagent chat --provider deepseek     # 强制 DeepSeek
polyagent chat --provider mock         # 强制 Mock
polyagent run --provider deepseek "分析订单"
```

---

## 二、整体架构速览

```
polyagent/
├── __init__.py          # 根包，版本号
├── config.py            # 配置加载（.env 文件）
│
├── core/                # 核心层 — 领域类型 + 单 Agent
│   ├── types.py         # Message, Role, AgentSpec, Usage, CostReport
│   ├── agent.py         # Agent 类（单 Agent 对话 + 工具循环）
│   └── exceptions.py    # 自定义异常
│
├── llm/                 # LLM 层 — Provider + 中间件链
│   ├── client.py        # LLMClient（含中间件链）
│   ├── provider.py      # LLMProvider 协议
│   ├── mock.py          # MockProvider（离线测试用）
│   ├── deepseek.py      # DeepSeekProvider（真实调用）
│   ├── middleware.py     # 中间件链（限流/重试/降级/预算/成本）
│   └── types.py         # LLMRequest, LLMResponse
│
├── tools/               # 工具系统
│   ├── base.py          # Tool 基类, ToolResult
│   ├── registry.py      # ToolRegistry, with_builtins
│   ├── builtins.py      # 内置工具（WebSearch, PythonExecute 等）
│   └── sandbox.py       # DockerSandbox, PathGuard
│
├── memory/              # 记忆系统
│   ├── base.py          # Memory 基类, MemoryRecord
│   ├── buffer.py        # ConversationBuffer（滑动窗口）
│   ├── compressor.py    # SummarizingCompressor, TokenWindowCompressor
│   └── vector_memory.py # VectorMemory（向量记忆）
│
├── rag/                 # RAG 系统
│   ├── embedder.py      # Embedder, HashEmbedder, FastEmbedEmbedder
│   ├── vectorstore.py   # VectorStore, InMemoryVectorStore, ChromaVectorStore
│   ├── splitter.py      # TextSplitter
│   └── index.py         # Document, RAGIndex
│
├── orchestration/       # 编排层（核心差异化能力）
│   ├── orchestrator.py  # Orchestrator（完整流水线调度器）
│   ├── roles.py         # Planner, Worker, Critic, Synthesizer
│   └── types.py         # RunResult, TaskNode, TaskStatus, Critique
│
├── observability/       # 可观测层
│   ├── tracer.py        # Tracer, Span（链路追踪）
│   ├── metrics.py       # Metrics
│   ├── logging.py       # configure_logging, get_logger
│   ├── middleware.py    # ObservabilityMiddleware
│   ├── exporters.py     # OTLP / Prometheus 导出
│   └── report.py        # RunReport
│
├── persistence/         # 持久化
│   ├── store.py         # RunStore（SQLite 运行记录）
│   └── chat_store.py    # ChatStore（SQLite 对话历史）
│
├── eval/                # 评测系统
│   ├── types.py         # EvalCase, EvalResult, EvalReport
│   ├── dataset.py       # Dataset
│   ├── scorers.py       # Scorer, ExactMatchScorer, ContainsScorer, LLMJudgeScorer
│   └── runner.py        # EvalRunner
│
└── skills/              # 技能系统（动态安装）
    ├── registry.py      # BUILTIN_SKILLS, list_skills, search_skills
    └── installer.py     # install_builtin, install_from_url, load_skills_into
```

---

## 三、模块逐个详解 + 代码示例

### 3.1 核心层 — core

#### 导入方式

```python
from polyagent.core.types import AgentSpec, Message, Role, Usage, CostReport
from polyagent.core.agent import Agent
from polyagent.core.exceptions import LLMError, RateLimitError, TimeoutError
```

#### AgentSpec — Agent 配置规格

```python
spec = AgentSpec(
    name="assistant",          # Agent 名称
    role="通用助手",            # 角色描述（planner/worker/critic/synthesizer 等）
    system_prompt="你是一个有用的助手。",  # 系统提示词
    model="deepseek-chat",     # 模型名
    temperature=0.7,           # 温度
    max_retries=3,             # 最大重试次数
)
```

#### Message — 消息结构

```python
from polyagent.core.types import Message, Role

msg = Message(role=Role.USER, content="你好")
# Role 枚举: SYSTEM, USER, ASSISTANT, TOOL
```

#### Usage / CostReport — Token 用量与成本

```python
usage = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
cost = CostReport()
cost.add_usage(usage, model="deepseek-chat")
print(cost.estimated_cost_usd)  # 输出美元金额
```

#### Agent — 单 Agent（最常用的基础 API）

```python
from polyagent.core.agent import Agent
from polyagent.core.types import AgentSpec
from polyagent.llm.client import LLMClient
from polyagent.llm.mock import MockProvider  # 离线测试用

client = LLMClient(MockProvider())

agent = Agent(
    spec=AgentSpec(name="helper", role="通用助手", model="deepseek-chat"),
    client=client,
)

result = await agent.run("用一句话解释多智能体系统")
print(result.content)       # AI 回复文本
print(result.usage)         # Usage(prompt_tokens=..., ...)
print(result.finish_reason) # "stop"
```

> **带 Tool 的 Agent（高级用法，见 3.4 工具系统）**

---

### 3.2 LLM 层 — llm

#### 导入方式

```python
from polyagent.llm import (
    LLMClient,          # LLM 客户端
    LLMProvider,        # Provider 协议
    LLMRequest,         # 请求体
    LLMResponse,        # 响应体
    MockProvider,       # 离线 Mock
    DeepSeekProvider,   # 真实 DeepSeek
    Middleware,          # 中间件协议
    RateLimitMiddleware, # 限流
    RetryMiddleware,     # 重试
    FallbackMiddleware,  # 降级
    BudgetMiddleware,    # 预算控制
    CostAccountMiddleware,  # 成本统计
    build_chain,        # 构建中间件链
)
```

#### MockProvider — 离线 Mock

```python
from polyagent.llm.mock import MockProvider

# 简单回显模式（把用户输入加 "[mock]" 前缀返回）
provider = MockProvider()

# 预置脚本模式（按顺序返回固定回复）
from polyagent.llm.types import LLMResponse, Usage
from polyagent.core.types import Usage

provider = MockProvider(
    script=[
        LLMResponse(content="第一轮回复", model="mock", usage=Usage(total_tokens=10)),
        LLMResponse(content="第二轮回复", model="mock", usage=Usage(total_tokens=10)),
    ],
    default=LLMResponse(content="默认回复", model="mock", usage=Usage(total_tokens=5)),
)
```

#### DeepSeekProvider — 真实调用

```python
from polyagent.llm.deepseek import DeepSeekProvider

# 需要设置环境变量 DEEPSEEK_API_KEY
provider = DeepSeekProvider(
    model="deepseek-chat",   # 或 "deepseek-reasoner"
    timeout=60.0,
)
```

#### LLMClient — 带中间件链的客户端

```python
from polyagent.llm import LLMClient, RetryMiddleware, RateLimitMiddleware

client = LLMClient(
    provider=DeepSeekProvider(),
    middlewares=[
        RateLimitMiddleware(max_calls=10, window_seconds=60),  # 60 秒最多 10 次
        RetryMiddleware(max_retries=3),                          # 失败重试 3 次
    ],
)

# 直接调底层（不通过 Agent）
request = LLMRequest(model="deepseek-chat", messages=[...])
response = await client.chat(request)
```

#### 完整中间件链说明

```
请求进入
  ↓
RateLimitMiddleware    — 限流（超限报错）
RetryMiddleware        — 重试（指数退避）
FallbackMiddleware     — 降级（主 provider 挂了切备用）
BudgetMiddleware       — 预算校验（超预算拒绝请求）
CostAccountMiddleware  — 成本累加
  ↓
provider.chat(request)  — 真实 LLM 调用
```

---

### 3.3 编排层 — orchestration ⭐（核心差异化）

#### 导入方式

```python
from polyagent.orchestration import Orchestrator, Planner, Worker, Critic, Synthesizer
from polyagent.orchestration import RunResult, TaskNode, TaskStatus, Critique
```

#### Orchestrator — 完整流水线

```python
from polyagent.core.agent import Agent
from polyagent.core.types import AgentSpec
from polyagent.llm.client import LLMClient
from polyagent.llm.mock import MockProvider
from polyagent.orchestration import Orchestrator, Planner, Worker, Critic, Synthesizer

client = LLMClient(MockProvider())

# 1. 创建四个角色 Agent
planner_agent = Agent(
    spec=AgentSpec(name="planner", role="planner",
                   system_prompt="你是一个任务规划专家。"),
    client=client,
)
worker_agent = Agent(
    spec=AgentSpec(name="worker", role="worker",
                   system_prompt="你是一个执行专家。"),
    client=client,
)
critic_agent = Agent(
    spec=AgentSpec(name="critic", role="critic",
                   system_prompt="你是一个质量评审专家。"),
    client=client,
)
synth_agent = Agent(
    spec=AgentSpec(name="synthesizer", role="synthesizer",
                   system_prompt="你是一个汇总专家。"),
    client=client,
)

# 2. 组装编排器
orchestrator = Orchestrator(
    planner=Planner(planner_agent),
    worker=Worker(worker_agent),
    critic=Critic(critic_agent),
    synthesizer=Synthesizer(synth_agent),
    max_concurrency=4,        # 最大并行 Worker 数
    max_review_retries=2,     # Critic 最多重审次数
)

# 3. 运行
result = await orchestrator.run("分析这个电商系统的订单流程")
print(result.answer)                  # 最终答案
print(result.latency)                 # 耗时（秒）
print(result.total_attempts)          # 总尝试次数
print(result.estimated_cost_usd)      # 估算成本（美元）
print(result.task_graph)              # 任务 DAG
```

#### 流水线执行流程

```
Planner（拆解任务为 DAG）
    ↓
Workers（并行执行子任务，semaphore 控制并发）
    ↓
Critic（评审每个结果，不通过则回退重试，上限 max_review_retries）
    ↓
Synthesizer（汇总所有通过的结果为最终答案）
```

---

### 3.4 工具系统 — tools

#### 导入方式

```python
from polyagent.tools import (
    Tool, ToolResult,            # 基类
    ToolRegistry, with_builtins, # 注册器
    WebSearch, PythonExecute,    # 内置工具
    ReadFile, WriteFile,
    GrepFiles, HttpRequest,
    DockerSandbox, PathGuard,    # 沙箱
)
```

#### 内置工具列表

```python
# Web 搜索（默认 Bing，支持 DuckDuckGo/搜狗）
WebSearch(engine="bing")   # engine: "bing" | "duckduckgo" | "sogou"

# 代码/Shell 执行
PythonExecute(sandbox=DockerSandbox())  # 安全执行 Python
```

#### 给 Agent 挂载工具

```python
from polyagent.tools.registry import with_builtins
from polyagent.core.agent import Agent
from polyagent.core.types import AgentSpec

agent_with_tools = Agent(
    spec=AgentSpec(name="coder", role="编程助手"),
    client=client,
    tools=with_builtins(),  # 挂载所有内置工具
    max_tool_iters=10,      # 最多 10 轮工具循环
)

result = await agent_with_tools.run("搜索 Python 3.13 的新特性")
# Agent 会自动判断是否需要调用 WebSearch
```

#### 自定义工具

```python
from polyagent.tools.base import Tool, ToolResult

class MyCustomTool(Tool):
    @property
    def definition(self) -> dict:
        return {
            "name": "my_custom_tool",
            "description": "做一件自定义的事",
            "parameters": {
                "type": "object",
                "properties": {
                    "input_param": {"type": "string", "description": "输入参数"},
                },
                "required": ["input_param"],
            },
        }

    async def execute(self, **kwargs) -> ToolResult:
        param = kwargs["input_param"]
        return ToolResult(output=f"处理了: {param}")
```

#### DockerSandbox — 安全执行环境

```python
from polyagent.tools.sandbox import DockerSandbox

# Docker 容器内安全执行代码
sandbox = DockerSandbox(
    image="python:3.13-slim",
    network_disabled=True,   # 禁止网络
    memory_limit="512m",     # 内存限制
    cpu_limit=1.0,           # CPU 限制
)

# 在 Agent 中使用
agent = Agent(
    spec=AgentSpec(name="safe_coder", role="安全执行"),
    client=client,
    tools=ToolRegistry([
        PythonExecute(sandbox=sandbox),  # 在沙箱里执行 Python
    ]),
)
```

---

### 3.5 记忆系统 — memory

#### 导入方式

```python
from polyagent.memory import (
    Memory, MemoryRecord,
    ConversationBuffer,          # 滑动窗口记忆
    SummarizingCompressor,       # 摘要压缩
    TokenWindowCompressor,       # Token 窗口截断
    VectorMemory,                # 向量记忆
)
```

#### ConversationBuffer — 滑动窗口

```python
buffer = ConversationBuffer(max_messages=20)  # 保留最近 20 条

record = MemoryRecord(role="user", content="你好")
buffer.add(record)

history = buffer.get_context()   # 返回最近 N 条
```

#### SummarizingCompressor — 摘要压缩

```python
compressor = SummarizingCompressor(
    client=LLMClient(MockProvider()),  # 用 LLM 做摘要
    max_tokens=500,
)
summary = await compressor.compress(long_history)
```

#### VectorMemory — 向量记忆

```python
vm = VectorMemory(dimension=384)  # 需要嵌入器
vm.add(MemoryRecord(role="user", content="我喜欢 Python"))
results = vm.search("编程语言", top_k=3)
```

---

### 3.6 RAG 系统 — rag

#### 导入方式

```python
from polyagent.rag import (
    Embedder, HashEmbedder, FastEmbedEmbedder,
    VectorStore, InMemoryVectorStore, ChromaVectorStore,
    TextSplitter,
    Document, RAGIndex,
)
```

#### 完整 RAG 流程

```python
from polyagent.rag import RAGIndex, TextSplitter, HashEmbedder, InMemoryVectorStore

# 1. 构建索引
index = RAGIndex(
    embedder=HashEmbedder(),                               # 离线嵌入（Mock）
    vector_store=InMemoryVectorStore(),                    # 内存向量库
    # 真实场景改用:
    # embedder=FastEmbedEmbedder(model="paraphrase-multilingual-MiniLM"),
    # vector_store=ChromaVectorStore(persist_directory="./chroma_data"),
)

# 2. 添加文档
index.add_documents([
    Document(id="d1", content="Python 是一种编程语言"),
    Document(id="d2", content="JavaScript 用于 Web 开发"),
])

# 3. 检索
results = index.query("编程语言", top_k=2)
for doc, score in results:
    print(f"{doc.content} (score: {score})")
```

#### TextSplitter — 文本分割

```python
splitter = TextSplitter(chunk_size=200, chunk_overlap=20)
chunks = splitter.split("很长很长的文本...")
```

---

### 3.7 可观测层 — observability

#### 导入方式

```python
from polyagent.observability import (
    configure_logging, get_logger,
    Tracer, Span,
    Metrics,
    ObservabilityMiddleware,
    RunReport,
)
```

#### 结构化日志

```python
from polyagent.observability import configure_logging, get_logger

configure_logging(level="INFO")
logger = get_logger("my_app")
logger.info("启动了", task="分析订单")
```

#### 链路追踪（Tracer）

```python
from polyagent.observability.tracer import Tracer

tracer = Tracer(service_name="polyagent")

with tracer.span("main_task", task_id="123"):
    with tracer.span("sub_task_1"):
        # 做一些工作
        pass
    with tracer.span("sub_task_2"):
        pass

# 导出到 Jaeger
from polyagent.observability import export_traces_to_otlp
count = export_traces_to_otlp(tracer, endpoint="http://localhost:4318/v1/traces")
```

#### 可观测中间件（自动追踪 LLM 调用）

```python
from polyagent.observability.middleware import ObservabilityMiddleware
from polyagent.observability.tracer import Tracer

client = LLMClient(
    provider=DeepSeekProvider(),
    middlewares=[ObservabilityMiddleware(tracer=Tracer(service_name="my_app"))],
)
# 此后所有 LLM 调用自动生成 span
```

---

### 3.8 持久化 — persistence

#### 导入方式

```python
from polyagent.persistence import RunStore, ChatStore
```

#### RunStore — 运行记录

```python
store = RunStore(db_path="./polyagent.db")

# 保存运行记录
await store.save_run(result, task="分析订单")

# 查询历史
runs = await store.list_runs(limit=10)
for run in runs:
    print(run.task, run.latency)
```

#### ChatStore — 对话历史

```python
store = ChatStore(db_path="./chat.db")

await store.save_messages("session_1", [msg1, msg2])
last_session = await store.load_last_session("session_1")
```

---

### 3.9 评测系统 — eval

#### 导入方式

```python
from polyagent.eval import (
    EvalCase, EvalResult, EvalReport,
    Dataset,
    Scorer, ExactMatchScorer, ContainsScorer, LLMJudgeScorer,
    EvalRunner,
)
```

#### 完整评测流程

```python
from polyagent.eval import Dataset, EvalRunner, ExactMatchScorer

# 1. 定义评测数据
dataset = Dataset(
    cases=[
        EvalCase(input="1+1=?", expected="2"),
        EvalCase(input="Python 的作者是?", expected="Guido van Rossum"),
    ]
)

# 2. 定义评分器
scorer = ExactMatchScorer()

# 3. 运行评测
runner = EvalRunner(
    subject=lambda inp: "2",  # 被测对象（可以是 Agent、Orchestrator 等）
    dataset=dataset,
    scorers=[scorer],
)
report = await runner.run()
print(f"Score: {report.score} / {report.total}")
```

---

### 3.10 技能系统 — skills

```python
from polyagent.skills import (
    BUILTIN_SKILLS,
    list_skills, search_skills,
    install_builtin, install_from_url,
    load_skills_into,
)
```

---

### 3.11 CLI 命令行（开箱即用）

安装后终端直接使用：

```bash
# 运行完整编排流水线（Mock 模式）
polyagent run "分析这个项目"

# 指定 DeepSeek 真实运行
polyagent run --provider deepseek "分析订单流程"

# 持久化保存运行结果
polyagent run --persist "分析订单"

# 流式输出
polyagent run --stream "写一首诗"

# 聊天模式（拟人化，隐藏技术细节）
polyagent chat

# 开发者模式（显示工具调用过程）
polyagent shell

# 查看历史运行记录
polyagent runs show

# 跑评测
polyagent eval --dataset eval_data.json

# 版本号
polyagent version
```

---

## 四、常见使用模式速查

### 模式 1：最简单 — 单 Agent 对话

```python
import asyncio
from polyagent.core.agent import Agent
from polyagent.core.types import AgentSpec
from polyagent.llm.client import LLMClient
from polyagent.llm.mock import MockProvider

async def main():
    agent = Agent(
        spec=AgentSpec(name="assistant", role="助手"),
        client=LLMClient(MockProvider()),
    )
    result = await agent.run("你是谁？")
    print(result.content)

asyncio.run(main())
```

### 模式 2：带工具的 Agent

```python
agent = Agent(
    spec=AgentSpec(name="researcher", role="研究员"),
    client=LLMClient(MockProvider()),
    tools=with_builtins(),
)
result = await agent.run("搜索一下最近的 AI 新闻")
```

### 模式 3：完整编排流水线

```python
orchestrator = Orchestrator(
    planner=Planner(planner_agent),
    worker=Worker(worker_agent),
    critic=Critic(critic_agent),
    synthesizer=Synthesizer(synth_agent),
)
result = await orchestrator.run("分析这个仓库的架构")
```

### 模式 4：有可观测的流水线

```python
tracer = Tracer(service_name="analysis")
orchestrator = Orchestrator(
    planner=Planner(planner_agent),
    worker=Worker(worker_agent),
    critic=Critic(critic_agent),
    synthesizer=Synthesizer(synth_agent),
    tracer=tracer,
)
result = await orchestrator.run("做分析")
export_traces_to_otlp(tracer, "http://localhost:4318/v1/traces")
```

### 模式 5：RAG 知识库 + 检索

```python
index = RAGIndex(
    embedder=HashEmbedder(),
    vector_store=InMemoryVectorStore(),
)
index.add_documents([Document(id="doc1", content="...")])
results = index.query("问题", top_k=3)
```

---

## 五、依赖关系一览

| 层级 | 依赖 |
|------|------|
| 必须 | pydantic>=2.6, pydantic-settings>=2.2, httpx>=0.27, typer>=0.12, structlog>=24.1, anyio>=4.3 |
| RAG（可选） | chromadb>=0.5, fastembed>=0.3, sentence-transformers>=3.0 |
| 可观测（可选） | opentelemetry-sdk>=1.25, opentelemetry-exporter-otlp-proto-http>=1.25, prometheus_client>=0.20 |
| 开发（可选） | pytest>=8, pytest-asyncio>=0.23, ruff>=0.5, mypy>=1.10 |

```bash
pip install scgnb666                    # 最小安装
pip install scgnb666[rag]               # +RAG
pip install scgnb666[observability]     # +可观测
pip install scgnb666[rag,observability] # +全部
```

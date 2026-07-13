# PolyAgent — 多智能体协作框架（项目规划 v1）

> 状态：规划稿（待确认后进入 M0 实现）
> 作者：Senior Developer（高级开发工程师）
> 日期：2026-07-10

---

## 0. 项目定位与价值主张（WHY）

### 痛点（为什么做）
单 Agent 直接调 LLM 写复杂任务，有三个无法回避的工程问题：
1. **上下文爆炸**：一个 Agent 既要规划又要执行还要汇总，prompt 越堆越长，成本与幻觉同步上升。
2. **单点不可靠**：模型偶尔抽风、超时、限流，没有重试/降级，整个任务直接崩。
3. **不可观测、不可评测**：跑完不知道花了多少 token、哪一步慢、质量如何，没法迭代优化。

### 方案（做什么）
一个**模型无关**的多智能体编排框架。用户声明式定义若干 Agent 角色 → 编排器按
`规划(Planner) → 并行执行(Workers) → 评审(Critic) → 汇总(Synthesizer)`
的流水线调度；每一层都挂**可靠性中间件**（重试 / 降级 / 限流 / token 预算）与**可观测埋点**；
工具、记忆、RAG 全部可插拔。交付为 **可 `import` 的 SDK + 配套 CLI**。

### 简历叙事（怎么讲）
> "我设计并实现了一个模型无关的多智能体协作框架，通过角色分工 + 编排层 + 可靠性中间件，
> 把不可控的 LLM 调用变成可调度、可降级、可观测的生产级系统；并附带一个代码仓库分析的 showcase 验证。"

这不是「调几个 API 的脚本」，而是有抽象层、中间件链、可测试、可观测的**框架**。

---

## 1. 技术选型

| 维度 | 选型 | WHY |
|---|---|---|
| 语言 | Python 3.13（managed 3.13.12） | 环境已具备；类型标注 + async 工程成熟 |
| 数据模型/配置 | pydantic v2 | 配置校验 + 自动 JSON Schema 生成（工具调用用） |
| 并发 | asyncio | 多 Worker 并行执行子任务 |
| LLM 抽象 | 自研 provider 层（OpenAI 兼容协议） | 统一 message 协议；默认实现 **DeepSeek**，预留 OpenAI/Anthropic 接口 |
| 工具调用 | 自研 Tool 基类 + registry + schema 自动生成 | 用 pydantic 模型自动生成 function-calling schema，零手写 JSON |
| 记忆/RAG | 短期 in-memory；长期向量抽象（默认 chromadb / sqlite+本地 embedding，可插拔） | 抽象优先，不绑死具体向量库 |
| 可观测 | structlog + 自研 tracer（span 树）+ 指标 | 不依赖重平台，离线可跑 |
| CLI | typer | 类型安全、自动 help |
| 测试 | pytest + pytest-asyncio + mock provider | **默认离线可跑**，不依赖真实 Key |
| 工程 | pyproject.toml（uv）、ruff、mypy、类型标注 | 生产级工程素养 |
| 包名（建议） | `polyagent` | 多智能体 = poly + agent |

---

## 2. 系统架构

### 2.1 分层架构
```
polyagent/
├── core/           # Agent 基类、Message/Role、RunResult、异常
├── llm/            # Provider 抽象、DeepSeek 实现、路由、可靠性中间件
├── tools/          # Tool 基类、registry、schema 生成、内置工具、沙箱
├── memory/         # 短期记忆、向量记忆、上下文压缩
├── rag/            # 文档加载、切分、embedding、检索
├── orchestration/  # 编排器：流水线、角色路由、并发、评审回退
├── observability/  # tracer、metrics、structured logs
├── eval/           # 数据集、评分器、回归
├── cli/            # typer 命令：run / chat / eval
└── examples/       # 代码仓库分析 showcase + 配置
```

### 2.2 多智能体协作流水线（核心亮点）
```
用户目标
   │
   ▼
[Planner]   拆解为目标 DAG（子任务 + 依赖关系）
   │
   ▼ 并发调度（受 semaphore 限流）
[Workers ×N]  按角色并行执行子任务，各持专属工具集
   │
   ▼
[Critic]    验收每个子任务产出；不达标则回退重做（含最大重试）
   │
   ▼
[Synthesizer]  汇总最终结果 + 成本/耗时报告
```
编排层负责：任务 DAG 调度、Worker 并发度、失败重试、模型降级、成本统计。

### 2.3 可靠性中间件链（LLM 层）
```
request → [限流] → [重试(指数退避)] → [降级(主→备模型)] → [token 预算校验] → provider → [成本统计] → response
```
每一环都是可组合的中间件（类 middleware 模式），便于单测与扩展。

### 2.4 核心数据模型（初版）
- `Message(role, content, tool_calls?, ...)` — 统一消息协议
- `AgentSpec(name, role, system_prompt, tools, model, max_retries, ...)`
- `TaskNode(id, description, deps, assignee, status, result)`
- `RunResult(answer, trace, cost, latency, task_graph)`

---

## 3. 目录结构（M0 落地）
```
polyagent/            # 包根
  __init__.py
  core/ ...
  llm/ ...
  ...
pyproject.toml
README.md
tests/
examples/repo_analysis/
docs/ARCHITECTURE.md
```

---

## 4. 实现里程碑（M0–M8）

| 里程碑 | 目标 | 关键交付物 | 验收标准 |
|---|---|---|---|
| **M0 脚手架** | 工程骨架 | pyproject、目录、ruff/mypy 配置、README 骨架、GitHub Actions(测试) | `pytest` 空跑通过；`polyagent` 可 import |
| **M1 LLM 层** | Provider 抽象 + 单 Agent 跑通 | `llm/provider.py`、DeepSeek 实现、Mock provider、可靠性中间件 | Mock 下单 Agent 完成一轮对话；重试/降级单测通过 |
| **M2 工具系统** | Tool 注册 + schema 自动生成 + 沙箱 | `tools/`、内置工具（代码执行/文件读写/HTTP/搜索）、registry | pydantic 模型 → JSON Schema 自动生成；工具可被 Agent 调用 |
| **M3 记忆 + RAG** | 短期/长期记忆 + 检索 | `memory/`、`rag/`、向量抽象 + 默认实现 | 多轮对话记忆生效；文档可被切分/嵌入/检索 |
| **M4 编排器** | 多智能体流水线 | `orchestration/`、Planner/Worker/Critic/Synthesizer、并发 + 评审回退 | 给定复杂目标，4 角色协作产出结果；Critic 回退生效 |
| **M5 可观测** | tracing/metrics/logs | `observability/`、span 树、结构化日志、成本统计 | 一次 run 产出完整 trace + 成本报告 |
| **M6 CLI** | 命令行入口 | `cli/`（run/chat/eval） | `polyagent run --goal "..."` 可跑通完整流水线 |
| **M7 Eval** | 数据集 + 评分 + 回归 | `eval/`、评分器、样例数据集 | `polyagent eval` 跑出分数；可作为回归基线 |
| **M8 文档 + 示例** | 收口 | `examples/repo_analysis`、ARCHITECTURE.md、README 简历亮点段 | 新人按 README 可复现 showcase |

---

## 5. 简历卖点映射（四大亮点全覆盖）
- **LLM 编排与可靠性** → `llm/` 中间件链、多模型路由、token 预算、成本统计
- **工具调用与插件** → `tools/` 自动 schema + 沙箱 + registry
- **记忆与 RAG** → `memory/` + `rag/`
- **可观测性与评测** → `observability/` + `eval/`
- **多智能体架构**（定位加成） → `orchestration/`

---

## 6. 工程与质量标准
- 每个里程碑配套 pytest 单测，**默认离线可跑**（Mock provider）
- 类型标注 100% 覆盖公开 API；ruff 无 error
- 每个模块有 docstring + 关键路径有 tracing
- 不写炫技代码：每个抽象都服务于「可复用 / 可测试 / 可观测」之一

---

## 7. 我需要你提供的 / 待确认
1. **项目命名**：我建议 `polyagent`（框架通用名）；若你想换（如 `RepoMind` 偏场景）告诉我。
2. **DeepSeek API Key**：联调端到端（M1 后期 / M4 后）才需要；**Mock 阶段不需要**，你可稍后给。
3. **示例 codebase**：代码仓库分析 showcase 我打算用公开 repo（如 `requests`/`flask`）跑，无需你提供私有代码。
4. 其余决策我已用合理默认定下（见上），你不反对即照此执行。

---

## 8. 风险与取舍
- **不过度抽象**：provider / 向量库做抽象，但不提前支持 10 种实现，先 DeepSeek + Mock + 一个向量默认实现。
- **不绑前端**：纯后端，不引入任何 UI（你明确要求）。
- **先可跑再完美**：每里程碑都保证「能跑、能测」，避免半成品。

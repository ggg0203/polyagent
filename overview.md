# PolyAgent — 项目总览

> 纯后端、模型无关的多智能体协作框架。SDK + CLI。简历项目。
> 完成时间：2026-07-10。里程碑 M0–M8 全部交付。

## 做了什么

从零设计并实现了一个**多智能体编排框架**：用户给目标 → 编排器按
`Planner → Workers(并行) → Critic(评审回退) → Synthesizer` 流水线调度，
LLM 层挂可靠性中间件链（限流/重试/降级/token 预算/成本统计），全程可观测、可评测。
交付为可 `import` 的 Python SDK + `polyagent` CLI，纯后端无 UI。

## 关键决策

- **模型无关**：`LLMProvider` 协议 + 统一 `Message`/`ToolCall`，DeepSeek 与 Mock 都实现；默认 Mock，离线零依赖可跑。
- **可靠性做成中间件而非散落 try/except**：每环（Retry/RateLimit/Fallback/Budget/Cost）独立可组合可测，`sleep` 可注入让重试测试零延迟。
- **工具 schema 自动生成**：Tool 声明 pydantic `args_model`，OpenAI function-calling JSON Schema 由 `model_json_schema()` 派生，零手写 JSON。
- **可观测零侵入**：`contextvars` 维护 span 栈，`ObservabilityMiddleware` 让每个 LLM 调用自动嵌套成子 span，编排层只开顶层 span。
- **编排层不重复造可靠性**：重试/降级/成本全复用 LLM 层中间件，编排只管「谁先跑/谁并行/谁回退/谁汇总」。
- **评测与被测解耦**：`EvalRunner.subject = async(str)->str`，能测任意可调用对象（Agent / Orchestrator / 外部函数）。

## 里程碑（全绿）

| M | 内容 | 测试 |
|---|---|---|
| M0 | 脚手架（pyproject/9 子包/ruff/mypy/CI/typer CLI） | 3 |
| M1 | LLM 层（Provider 协议 + 中间件链 + Mock/DeepSeek + 单 Agent） | +12 |
| M2 | 工具系统（Tool→schema 自动生成 + 5 内置 + Agent tool loop） | +12 |
| M3 | 记忆+RAG（buffer/vector_memory/compressor + embedder/vectorstore/splitter/index） | +11 |
| M4 | 编排器（四角色 + DAG 调度 + 评审回退 + 失败阻断） | +4 |
| M5 | 可观测（Tracer span 树 + Metrics + structlog + 中间件埋点） | +4 |
| M6 | CLI（run/chat/eval/version + 离线 demo 编排器） | +4 |
| M7 | Eval（数据集 + 评分器 + Runner + polyagent eval） | +5 |
| M8 | 文档 + 代码仓库分析 showcase | — |

**总计 55 tests passing，ruff 全绿，全程离线 Mock，无需 API Key。**

## 文件结构

```
polyagent/        # 9 子包：core/llm/tools/memory/rag/orchestration/observability/eval/cli
tests/           # 8 测试文件，55 tests
examples/repo_analysis/  # 代码仓库分析 showcase（analyze.py）
docs/ARCHITECTURE.md     # 架构文档（数据模型/中间件链/流水线）
README.md        # 含简历亮点段 + 快速开始 + roadmap
PROJECT_PLAN.md  # 初始规划
```

## 简历亮点映射

- LLM 编排与可靠性 → `llm/`（中间件链 + 多模型路由 + token 预算 + 成本）
- 工具调用与插件 → `tools/`（自动 schema + 沙箱 + registry）
- 记忆与 RAG → `memory/` + `rag/`（可插拔 embedder/vectorstore）
- 可观测性与评测 → `observability/`（span 树）+ `eval/`（评测闭环）
- 多智能体协作架构 → `orchestration/`（四角色 DAG 流水线）

## 跑起来

```bash
pip install -e ".[dev]"
polyagent run "build a small web app"   # 多智能体流水线（mock）
polyagent eval                          # 评测 2/3 passed 67%
python examples/repo_analysis/analyze.py .  # 代码仓库分析 showcase
pytest -q                               # 55 tests
```

## 后续可扩展（未做，明确边界）

- DeepSeek 真实联调（CLI `--provider deepseek` 路径预留，接 Key 即用）
- 真实向量库（chromadb/pgvector 接 `VectorStore` 协议）
- LLMJudgeScorer（用模型评分，接 `Scorer` 协议）
- 真实 embedding（接 `Embedder` 协议，替换 HashEmbedder）

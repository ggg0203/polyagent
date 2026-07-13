# PolyAgent — 项目长期记忆

## 定位
模型无关的多智能体协作框架（纯后端 Python）。交付 = SDK + CLI。用途：简历项目。
痛点叙事：单 Agent 上下文爆炸 / 单点不可靠 / 不可观测不可评测 → 角色分工 + 编排层 + 可靠性中间件。

## 关键约定
- 命名：`polyagent`（poly=多 + agent）。
- Python：3.13，managed venv 路径 `C:/Users/孙/.workbuddy/binaries/python/envs/default`。
  - 运行：`.../Scripts/python.exe -m pytest` / `-m ruff check .`
- LLM：默认 DeepSeek（OpenAI 兼容协议）；**默认用 Mock provider**，离线可跑，真实 Key 联调时给。
- showcase：代码仓库分析（examples/repo_analysis，用公开 repo，M8 实现）。
- 工程纪律：每里程碑配 pytest（离线 Mock）；ruff 全绿；类型标注；不写炫技代码。

## 架构分层
core / llm / tools / memory / rag / orchestration / observability / eval / cli。
可靠性中间件链：限流→重试→降级→预算校验→provider→成本统计。
流水线：Planner → Workers(并行) → Critic(评审回退) → Synthesizer。

## 里程碑
- M0 脚手架 ✅（pyproject/setuptools, 9 子包, ruff/mypy, CI, typer CLI version, smoke 测试）
- M1 LLM 层 ✅（core: types/exceptions/agent；llm: provider/middleware/client/mock/deepseek；15 tests pass, ruff 全绿, 离线 Mock）
- M2 工具系统 ✅（tools: base/registry/builtins；Tool→OpenAI schema 自动生成；5 内置工具；Agent tool loop；Message/LLMRequest/LLMResponse 加 tool_calls/tools；deepseek 支持 tools；27 tests pass）
- M3 记忆+RAG ✅（memory: base/buffer/vector_memory/compressor；rag: embedder/vectorstore/splitter/index；HashEmbedder+InMemoryVectorStore 离线默认；38 tests pass）
- M4 编排器 ✅（orchestration: types/roles/orchestrator；Planner→Workers(并发)→Critic(评审回退 max_review_retries)→Synthesizer；任务 DAG 拓扑调度+失败阻断；RunResult(answer/task_graph/latency/total_attempts/cost)；42 tests pass）
- M5 可观测 ✅（observability: tracer(contextvars span 树)/metrics/structlog/RunReport/ObservabilityMiddleware；Orchestrator 加 tracer 埋点；端到端 trace+metrics+cost；46 tests pass）
- M6 CLI ✅（typer run/chat/eval/version + demo orchestrator 脚本化 Mock；`polyagent run` 离线跑通完整流水线；50 tests pass）
- M7 Eval ✅（eval: types/scorers/dataset/runner；ContainsScorer/ExactMatchScorer + Scorer 协议；EvalRunner subject 通用解耦；polyagent eval 跑出 2/3 67%；55 tests pass）
- M8 文档+示例 ✅（README 完整版含简历亮点段 + ARCHITECTURE 更新对齐实现 + repo_analysis showcase 可跑；55 tests 全绿）

## 企业级补强（M9–M14，用户要企业级/纯智能体/纯后端/完善）
- 选型：DeepSeek embedding API（实测 404 不支持 → 改 fastembed 本地 ONNX）+ Docker 容器沙箱 + 起容器验证可观测(OTLP+Prom) + .env 联调
- M9 真实可用性 ✅（pydantic-settings config 读 .env；DeepSeek stream 流式；LLMClient.stream/Agent.run_stream/MockProvider.stream；CLI run --provider deepseek + chat --stream；真实联调：run cost $0.000763>0、chat 流式输出；55 tests）
- M10 持久化 ✅（persistence/store.py sqlite RunStore save/list/get run+tasks+trace；CLI run --persist 默认存 + runs/show 查历史；58 tests）
- M11 可观测后端 ✅（exporters: OTLP trace→OTel SDK 导出 + Prom→pushgateway；config ObservabilitySettings；cli run 配 endpoint 自动导出；docker-compose Jaeger+pushgateway+prometheus；60 tests；**真 Jaeger 验证通过**：docker run jaeger + polyagent run → Jaeger API 返回 polyagent 服务 + span 树(planner.plan 等带父子关系)，Exported 10 spans）
- M12 RAG真实化 ✅（FastEmbedEmbedder 真实语义 ONNX(paraphrase-multilingual-MiniLM) + ChromaVectorStore 持久化；DeepSeek 无 embedding API 实测 404 改 fastembed；联调 query「编程语言」→ 编程相关 d1/d2 score 远高于天气 d3；60 tests）
- M13 沙箱 ✅（tools/sandbox.py DockerSandbox 容器执行 --network=none --memory --cpus + PathGuard 路径白名单；PythonExecute 加 sandbox 参数注入；真 docker 联调 5 tests pass；65 tests）
- M14 质量收口 ✅（mypy strict 0 错 + pytest-cov 77% 门禁 75% + LLMJudgeScorer + Dockerfile + docker-compose polyagent profile + CI 强制 mypy/coverage）
- **🎉 企业级补强 M9–M14 全部完成。65 tests，mypy strict 全绿，coverage 77%，ruff 全绿。真实联调全通过：DeepSeek run cost>0、流式 chat、Jaeger span 树、FastEmbed 语义检索、Docker 沙箱。**

## 踩坑备忘
- typer 单命令模式：app 仅一个 command 时变单命令 app，需加空 `@app.callback()` 回 group 模式。
- ruff isort(I001)：first-party import 排序/分组要求重排，用 `ruff check --fix` 自动修。
- ruff E501(line-length=100)：长链式调用拆成局部变量再传参。

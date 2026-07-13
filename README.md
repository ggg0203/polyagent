# PolyAgent

> A **model-agnostic multi-agent orchestration framework** — declare Agent roles,
> let the orchestrator run them through a `Plan → Execute(parallel) → Critique → Synthesize`
> pipeline, with reliability middleware and observability at every layer.

[![CI](https://github.com/OWNER/polyagent/actions/workflows/ci.yml/badge.svg)](./.github/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Tests](https://img.shields.io/badge/tests-55%20passing-brightgreen)

`polyagent` is a pure-backend, dependency-light Python framework for building
**multi-agent systems on top of LLMs**. It ships as a reusable **SDK** plus a
**CLI**. No UI, no web framework — just orchestration.

---

## Why

A single agent calling an LLM directly hits three walls on real work:

1. **Context explosion** — one agent planning + executing + summarizing balloons the prompt.
2. **Single-point unreliability** — one timeout / rate-limit kills the whole task.
3. **No observability, no evaluation** — you can't tell what it cost or how good it was.

PolyAgent answers this with **role separation + an orchestration layer + a
reliability middleware chain**, turning raw LLM calls into a schedulable,
degradable, observable system.

---

## Install

```bash
# editable install with dev tooling
pip install -e ".[dev]"

# (optional) RAG extras — heavier vector backends
pip install -e ".[rag]"
```

Requires Python ≥ 3.11.

## Quick start

```bash
polyagent version                       # sanity check
polyagent run "build a small web app"   # run the full multi-agent pipeline (mock, offline)
polyagent eval                          # run the eval dataset, print pass-rate
polyagent chat                          # interactive single-agent chat (Ctrl-D to exit)
```

SDK usage:

```python
import asyncio
from polyagent.core import Agent, AgentSpec
from polyagent.llm import LLMClient, MockProvider
from polyagent.orchestration import Orchestrator, Planner, Worker, Critic, Synthesizer
from polyagent.observability import Tracer

async def main():
    tracer = Tracer()
    # ...assemble Planner/Worker/Critic/Synthesizer with LLMClients...
    orch = Orchestrator(planner, worker, critic, synth, tracer=tracer)
    result = await orch.run("your goal")
    print(result.answer, result.task_graph, result.estimated_cost_usd)

asyncio.run(main())
```

---

## Architecture

```
polyagent/
├── core/           # Agent, Message/Role/ToolCall, AgentSpec, exceptions
├── llm/            # LLMProvider protocol, DeepSeek/Mock, reliability middleware, LLMClient
├── tools/          # Tool base, registry, pydantic->JSON Schema, 5 built-ins, sandbox
├── memory/         # ConversationBuffer, VectorMemory, context compressors
├── rag/            # Embedder/VectorStore protocols, HashEmbedder, InMemoryVectorStore, TextSplitter, RAGIndex
├── orchestration/  # Planner/Worker/Critic/Synthesizer, DAG scheduler, critique retry
├── observability/  # Tracer(span tree), Metrics, structlog, ObservabilityMiddleware
├── eval/           # Dataset, Scorer, EvalRunner, EvalReport
└── cli/            # typer: run / chat / eval / version
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

### Reliability middleware chain (LLM layer)

```
request → RateLimit → Retry(backoff+jitter) → Fallback → BudgetCheck → provider → CostAccount → response
```

Each link is composable and unit-testable; `ObservabilityMiddleware` adds an `llm.chat` span per call.

---

## Roadmap — all done ✅

| Milestone | Status | What |
|---|---|---|
| M0 | ✅ | scaffold: pyproject, package tree, ruff/mypy, CI, smoke tests |
| M1 | ✅ | LLM provider abstraction + reliability middleware + single agent |
| M2 | ✅ | tool system + pydantic→schema + 5 built-ins + sandbox |
| M3 | ✅ | memory + RAG (pluggable embedder/vectorstore) |
| M4 | ✅ | orchestrator: 4-role pipeline + DAG + critique fallback |
| M5 | ✅ | observability: span-tree tracing + metrics + structured logs |
| M6 | ✅ | CLI: run / chat / eval / version |
| M7 | ✅ | eval: datasets + scorers + runner |
| M8 | ✅ | docs + repo-analysis showcase |

---

## Showcase: code repository analysis

```bash
python examples/repo_analysis/analyze.py .
```

A Planner decomposes "analyze repo" into `inventory → entrypoints → tests → smells → report`;
Workers carry `grep_files` + `read_file`; a Critic reviews; a Synthesizer writes the report.
Mock mode runs offline. See [examples/repo_analysis/README.md](examples/repo_analysis/README.md).

---

## Resume highlights

- **LLM orchestration & reliability** — provider protocol, DeepSeek + Mock,
  retry / fallback / rate-limit / token-budget / cost accounting (`llm/`).
- **Tool-use & plugins** — function-calling schema auto-generated from pydantic,
  registry, 5 built-in tools, subprocess sandbox (`tools/`).
- **Memory & RAG** — short-term buffer, vector memory, pluggable embedder/vectorstore,
  context compression (`memory/`, `rag/`).
- **Observability & evaluation** — contextvars span-tree tracing, metrics, structlog,
  eval datasets + scorers + pass-rate (`observability/`, `eval/`).
- **Multi-agent architecture** — role pipeline with DAG scheduling, parallel workers,
  critique-driven retry, failure blocking (`orchestration/`).

**The one-liner:** "A model-agnostic multi-agent orchestration framework that turns
raw LLM calls into a schedulable, degradable, observable, evaluable system — SDK + CLI,
55 offline tests, zero UI."

---

## Testing

```bash
pytest -q          # 55 tests, all offline (MockProvider)
ruff check .       # clean
```

CI runs on Python 3.11 / 3.12 / 3.13.

---

## License

MIT.

# Architecture

> Status: **M0–M8 complete.** Everything below is implemented and covered by
> 55 offline tests (ruff clean). What was "target" in early milestones is now shipped.

## 1. Design goals

1. **Model-agnostic** — no provider is hardcoded into core logic. Providers are
   pluggable behind a single `LLMProvider` protocol with a unified `Message` shape.
2. **Composable reliability** — retry / fallback / rate-limit / budget are
   middleware, not scattered `try/except`. Each is independently testable.
3. **Observable by default** — every agent step emits a trace span; a run always
   yields a cost + latency report.
4. **Offline-testable** — a `MockProvider` reproduces deterministic LLM behavior
   so the whole pipeline runs without network or API keys.
5. **No UI** — pure backend. SDK + CLI only.

## 2. Layered structure

```
                     ┌─────────────────────────────────────────┐
   user goal ──────▶ │            orchestration                │
                     │  Planner → Workers(parallel) → Critic → │ ──▶ RunResult
                     │            Synthesizer                   │   (answer+graph+cost)
                     └───────┬─────────────────────────────────┘
                             │ uses
            ┌────────────────┼────────────────────────┐
            ▼                ▼                        ▼
         core              tools                    memory/rag
   (Agent, Message,    (registry, schema,         (buffer, vector memory,
    ToolCall, exc)      built-ins, sandbox)        embedder, vectorstore,
                             │                      splitter, RAGIndex)
                             ▼
                          llm
   (Provider protocol + reliability middleware + ObservabilityMiddleware)
                             │
                             ▼
                 observability (Tracer span tree, Metrics, structlog)
```

## 3. Core data model (as implemented)

```python
class Message(BaseModel):
    role: Role                       # system | user | assistant | tool
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None

class ToolCall(BaseModel):
    id: str
    name: str
    arguments: str                  # JSON string (OpenAI convention)

class AgentSpec(BaseModel):
    name: str
    role: str                       # planner | worker | critic | synthesizer
    system_prompt: str = ""
    model: str = "deepseek-chat"
    temperature: float = 0.7
    max_retries: int = 3

class TaskNode(BaseModel):
    id: str
    description: str
    deps: list[str] = []
    status: TaskStatus = PENDING    # pending | running | done | failed
    result: str | None = None
    attempts: int = 0

class RunResult(BaseModel):
    answer: str
    task_graph: list[TaskNode]
    latency: float = 0.0
    total_attempts: int = 0
    estimated_cost_usd: float = 0.0
```

## 4. Reliability middleware chain

```
LLMRequest ─▶ [RateLimit] ─▶ [Retry(backoff+jitter)] ─▶ [Fallback] ─▶ [BudgetCheck]
            ─▶ Provider.chat() ─▶ [CostAccount] ─▶ LLMResponse
```

- **RateLimit** — concurrency cap (`asyncio.Semaphore`) + minimum spacing.
- **Retry** — exponential backoff + jitter; honours `RateLimitError.retry_after`. `sleep` injectable for tests.
- **Fallback** — primary handler fails → backup providers tried in order.
- **BudgetCheck** — aborts before a call if the run already consumed its token budget.
- **CostAccount** — accumulates per-response usage into a shared `CostReport` (model pricing table).
- **ObservabilityMiddleware** (M5) — wraps every call as an `llm.chat` span + bumps metrics.

Each middleware wraps the next; the chain is built once per `LLMClient`.

## 5. Multi-agent pipeline

```
goal
  │
  ▼
Planner        ── splits goal into a TaskNode DAG (with deps) as JSON
  │
  ▼  (asyncio.Semaphore caps concurrency)
Workers × N    ── each Worker (optionally) carries a tool set; runs in parallel
  │
  ▼
Critic         ── accepts/rejects each TaskNode; rejected → redo (max_review_retries)
  │
  ▼
Synthesizer    ── merges accepted results into the final answer
```

A task whose dependency **FAILED** is itself marked FAILED (no execution on broken input).
The orchestrator emits `orchestrator.run` / `planner.plan` / `schedule` / `task` /
`worker.execute` / `critic.review` / `synthesizer.synthesize` spans when a `Tracer` is attached.

## 6. Eval (M7)

`EvalRunner(subject, scorer)` runs a `Dataset` of `EvalCase`s: each case's `input`
goes through `subject` (any `async (str)->str`), the `Scorer` compares output to
`expected`. `EvalReport` aggregates `pass_rate` / `avg_score`. `polyagent eval` runs
the default dataset.

## 7. Testing strategy

- 55 unit/integration tests, **all offline** via `MockProvider`.
- CI (`.github/workflows/ci.yml`) runs ruff + pytest on Python 3.11/3.12/3.13.
- The eval harness doubles as a regression baseline.

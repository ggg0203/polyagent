# Repo Analysis Showcase

Demonstrates PolyAgent applied to **code repository analysis**.

## Run (offline, mock)

```bash
python examples/repo_analysis/analyze.py .
```

Prints a (mock) analysis report + task graph. Mock providers exercise the full
`Plan → Workers → Critic → Synthesizer` pipeline with no API key.

## What it shows

- **Planner** decomposes "analyze repo" into: `inventory → entrypoints → tests → smells → report` (a 5-node DAG).
- **Workers** hold the file tools (`grep_files`, `read_file`) — wired via `with_builtins()`.
- **Critic** reviews each step; **Synthesizer** writes the report.
- An `observability.Tracer` records the run; the summary prints task count + trace roots.

## Real analysis

A real analysis needs a live LLM. Set `DEEPSEEK_API_KEY`, switch `--provider deepseek`
(once the deepseek path is wired), and the workers will actually read the repo at
`--repo <path>` using the file tools.

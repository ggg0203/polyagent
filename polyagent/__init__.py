"""PolyAgent — a model-agnostic multi-agent orchestration framework.

Declare Agent roles, let the orchestrator run them through a
Plan -> Execute(parallel) -> Critique -> Synthesize pipeline, with
reliability middleware (retry / fallback / budget) and observability at every layer.
"""

__version__ = "0.1.2"

__all__ = ["__version__"]

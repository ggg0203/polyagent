"""Observability: tracer, metrics, structured logging, run report, LLM middleware, exporters."""

from polyagent.observability.logging import configure_logging, get_logger
from polyagent.observability.metrics import Metrics
from polyagent.observability.middleware import ObservabilityMiddleware
from polyagent.observability.report import RunReport
from polyagent.observability.tracer import Span, Tracer

__all__ = [
    "Metrics",
    "ObservabilityMiddleware",
    "RunReport",
    "Span",
    "Tracer",
    "configure_logging",
    "get_logger",
]


def export_traces_to_otlp(tracer: Tracer, endpoint: str) -> int:
    """Lazy import so the heavy opentelemetry deps are optional (observability extra)."""
    from polyagent.observability.exporters import export_traces_to_otlp as _export

    return _export(tracer, endpoint)


def export_metrics_to_prometheus(metrics: Metrics, pushgateway: str) -> int:
    from polyagent.observability.exporters import (
        export_metrics_to_prometheus as _export,
    )

    return _export(metrics, pushgateway)

"""Exporters — push the in-memory Tracer/Metrics to real backends.

- ``export_traces_to_otlp`` converts the Tracer span tree into OpenTelemetry spans
  and sends them via OTLP/HTTP to a collector (Jaeger, Tempo, …).
- ``export_metrics_to_prometheus`` pushes a Metrics snapshot to a Prometheus
  pushgateway.

Both are config-driven: only run if an endpoint is configured, otherwise the
in-memory Tracer/Metrics are used as before.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from polyagent.observability.metrics import Metrics
    from polyagent.observability.tracer import Tracer


def export_traces_to_otlp(tracer: Tracer, endpoint: str) -> int:
    """Export the Tracer span tree via OTLP/HTTP. Returns the number of spans sent."""
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.trace import set_span_in_context
    from opentelemetry.trace.status import Status, StatusCode

    provider = TracerProvider(resource=Resource.create({"service.name": "polyagent"}))
    provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    otel = provider.get_tracer("polyagent")

    sent = 0

    def walk(span, parent_ctx) -> None:  # type: ignore[no-untyped-def]
        nonlocal sent
        with otel.start_as_current_span(span.name, context=parent_ctx) as s:
            for key, val in span.attributes.items():
                with contextlib.suppress(Exception):
                    s.set_attribute(key, val)
            if span.error:
                s.set_status(Status(StatusCode.ERROR, span.error))
            else:
                s.set_status(Status(StatusCode.OK))
            sent += 1
            child_ctx = set_span_in_context(s)
            for child in span.children:
                walk(child, child_ctx)

    for root in tracer.roots:
        walk(root, None)
    provider.force_flush()
    provider.shutdown()
    return sent


def export_metrics_to_prometheus(metrics: Metrics, pushgateway: str) -> int:
    """Push a Metrics snapshot to a Prometheus pushgateway. Returns metrics pushed."""
    from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

    registry = CollectorRegistry()
    summary = metrics.summary()
    for name, value in summary.items():
        try:
            Gauge(name, name, registry=registry).set(float(value))
        except (TypeError, ValueError):
            continue
    push_to_gateway(pushgateway, job="polyagent", registry=registry)
    return len(summary)

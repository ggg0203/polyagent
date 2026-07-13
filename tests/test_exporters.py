"""Exporters: verify OTLP export actually sends spans to an OTLP/HTTP endpoint.

Uses a tiny in-process HTTP server that accepts the OTLP/HTTP POST and records
the body — proves the export path works without needing a real Jaeger container.
(Run `docker compose up jaeger` + set OTEL_EXPORTER_OTLP_ENDPOINT for a live Jaeger.)
"""

from __future__ import annotations

import http.server
import threading

from polyagent.observability import Tracer, export_traces_to_otlp


class _RecordingHandler(http.server.BaseHTTPRequestHandler):
    received: list[bytes] = []

    def do_POST(self) -> None:  # noqa: D401
        length = int(self.headers.get("content-length", 0))
        body = self.rfile.read(length)
        _RecordingHandler.received.append(body)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args: object) -> None:  # noqa: ARG002
        pass


def test_otlp_export_sends_spans() -> None:
    _RecordingHandler.received.clear()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        tracer = Tracer()
        with tracer.span("root", goal="test"), tracer.span("child"):
            pass
        sent = export_traces_to_otlp(tracer, f"http://127.0.0.1:{port}/v1/traces")
        assert sent == 2
        assert len(_RecordingHandler.received) >= 1  # OTLP POST actually sent
    finally:
        server.shutdown()


def test_otlp_export_empty_tracer() -> None:
    _RecordingHandler.received.clear()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        sent = export_traces_to_otlp(Tracer(), f"http://127.0.0.1:{port}/v1/traces")
        assert sent == 0
    finally:
        server.shutdown()

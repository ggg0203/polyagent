"""Tracer — nested span tree via contextvars.

A ``Tracer`` collects spans into a tree (root spans + their children). Entering
``tracer.span("name")`` pushes the span as the current span; nested calls become
its children automatically. Spans record duration, status, error, attributes.

Designed to be cheap: do nothing if the caller passes ``tracer=None`` and uses
``contextlib.nullcontext`` instead.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Span:
    name: str
    start: float = field(default_factory=time.monotonic)
    end: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    error: str | None = None
    children: list[Span] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return (self.end or time.monotonic()) - self.start

    def finish(self) -> None:
        self.end = time.monotonic()


_current_span: ContextVar[Span | None] = ContextVar("polyagent_current_span", default=None)


class Tracer:
    def __init__(self) -> None:
        self.roots: list[Span] = []

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[Span]:
        parent = _current_span.get()
        s = Span(name=name, attributes=dict(attrs))
        if parent is None:
            self.roots.append(s)
        else:
            parent.children.append(s)
        token = _current_span.set(s)
        try:
            yield s
            s.status = "ok"
        except Exception as exc:
            s.status = "error"
            s.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            s.finish()
            _current_span.reset(token)

    def to_dict(self) -> dict[str, Any]:
        return {"spans": [self._span_dict(s) for s in self.roots]}

    @staticmethod
    def _span_dict(s: Span) -> dict[str, Any]:
        return {
            "name": s.name,
            "duration_ms": round(s.duration * 1000, 3),
            "status": s.status,
            "error": s.error,
            "attributes": s.attributes,
            "children": [Tracer._span_dict(c) for c in s.children],
        }

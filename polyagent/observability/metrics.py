"""Metrics — lightweight counters + timing observations (no external backend)."""

from __future__ import annotations

from typing import Any


class Metrics:
    def __init__(self) -> None:
        self._counters: dict[str, float] = {}
        self._timings: dict[str, list[float]] = {}

    def inc(self, name: str, n: float = 1.0) -> None:
        self._counters[name] = self._counters.get(name, 0.0) + n

    def observe(self, name: str, value: float) -> None:
        self._timings.setdefault(name, []).append(value)

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = dict(self._counters)
        for name, values in self._timings.items():
            if not values:
                continue
            out[f"{name}.count"] = len(values)
            out[f"{name}.avg"] = sum(values) / len(values)
            out[f"{name}.max"] = max(values)
        return out
